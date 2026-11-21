from __future__ import annotations

import json

import pytest

from tabledoc import Options
from tabledoc.cli import main
from tabledoc.load import ALIAS, Target, attached, load
from tabledoc.report import Report, SpecError

DATASET = "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\n"
TABLE = "$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json\n"


@pytest.fixture
def catalog(tmp_path):
    """A DuckLake catalog with sales.orders, sales.extra and the view sales.recent."""
    path = tmp_path / "lake" / "work.sqlite"
    data = tmp_path / "lake" / "data"
    data.mkdir(parents=True)
    with attached(str(path), data.as_posix() + "/") as con:
        con.execute(f"CREATE SCHEMA {ALIAS}.sales")
        con.execute(f"CREATE TABLE {ALIAS}.sales.orders AS SELECT 1 AS id, 'a' AS file")
        con.execute(f"CREATE TABLE {ALIAS}.sales.extra AS SELECT 1 AS x")
        con.execute(f"CREATE VIEW {ALIAS}.sales.recent AS SELECT * FROM {ALIAS}.sales.orders")
    return path, data.as_posix() + "/"


def project(write):
    return write(
        {
            "tabledoc.yml": DATASET + "name: shop\ntitle: Shop\nlicenses: [CC-BY-4.0]\nqueria: {themes: [trade]}\n",
            "README.md": "Overview.\n",
            "sales/orders.yml": TABLE
            + "title: Orders\ndescription: One row is one order.\nprimary_key: [id]\n"
            + "columns:\n  - {name: id, description: The order, entity: {type: primary, name: order}}\n"
            + "  - {name: file, asset: true}\n",
            "sales/orders.md": "Guide.\n",
            "sales/recent.yml": TABLE + "description: The last orders.\n",
        }
    )


def query(path, data, sql):
    with attached(str(path), data) as con:
        return con.execute(sql).fetchall()


def test_writes_meta_comments_and_the_folder_for_fdl(write, catalog, tmp_path):
    path, data = catalog
    root = project(write)
    out = root / ".fdl" / "pack"
    report = Report()
    found = load(Options(root, with_source=False), Target(str(path), data, out, unlisted=True), report)
    assert found is not None, report.render()
    assert query(path, data, f"SELECT title, licenses[1].id, themes FROM {ALIAS}._meta.dataset") == [
        ("Shop", "CC-BY-4.0", ["trade"])
    ]
    assert query(path, data, f"SELECT schema, name, published FROM {ALIAS}._meta.tables ORDER BY name") == [
        ("sales", "extra", False),
        ("sales", "orders", None),
        ("sales", "recent", None),
    ]
    assert query(path, data, f"SELECT name, entity FROM {ALIAS}._meta.columns") == [("id", "order")]
    assert query(path, data, f"SELECT path, kind, \"table\" FROM {ALIAS}._meta.files ORDER BY path") == [
        ("README.md", "guide", None),
        ("sales/orders.md", "guide", "orders"),
    ]
    comments = f"SELECT comment FROM duckdb_tables() WHERE database_name = '{ALIAS}' AND table_name = 'orders'"
    assert query(path, data, comments) == [("One row is one order.",)]
    view = f"SELECT comment FROM duckdb_views() WHERE database_name = '{ALIAS}' AND view_name = 'recent'"
    assert query(path, data, view) == [("The last orders.",)]
    column = (
        f"SELECT comment FROM duckdb_columns() WHERE database_name = '{ALIAS}' "
        "AND table_name = 'orders' AND column_name = 'id'"
    )
    assert query(path, data, column) == [("The order",)]

    structure = json.loads((out / "dataset.json").read_text())
    assert structure["name"] == "shop"
    assert {"schema": "sales", "name": "orders", "primary_key": ["id"], "fields": [{"name": "file", "asset": True}]} in (
        structure["tables"]
    )
    assert {"schema": "_meta", "name": "files", "primary_key": ["path"], "fields": [{"name": "sha256", "asset": True}]} in (
        structure["tables"]
    )
    assert (out / "assets" / "files" / "README.md").read_text() == "Overview.\n"


def test_a_second_load_replaces_meta_and_clears_comments(write, catalog):
    path, data = catalog
    root = project(write)
    load(Options(root, with_source=False), Target(str(path), data), Report())
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders\n", encoding="utf-8")
    assert load(Options(root, with_source=False), Target(str(path), data), Report()) is not None
    assert query(path, data, f"SELECT count(*) FROM {ALIAS}._meta.columns") == [(0,)]
    comments = f"SELECT comment FROM duckdb_tables() WHERE database_name = '{ALIAS}' AND table_name = 'orders'"
    assert query(path, data, comments) == [(None,)]


def test_keeps_the_sql_without_a_build(write, catalog):
    path, data = catalog
    root = project(write)
    load(Options(root, with_source=False), Target(str(path), data), Report())
    with attached(str(path), data) as con:
        con.execute(f"UPDATE {ALIAS}._meta.tables SET sql = 'select 1', depends_on = ['sales.extra'] WHERE name = 'orders'")
    load(Options(root, with_source=False), Target(str(path), data), Report())
    assert query(path, data, f"SELECT sql, depends_on FROM {ALIAS}._meta.tables WHERE name = 'orders'") == [
        ("select 1", ["sales.extra"])
    ]


def test_a_table_not_in_the_catalog_writes_nothing(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "sales" / "gone.yml").write_text(TABLE + "title: Gone\n", encoding="utf-8")
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report) is None
    assert [f.code for f in report.findings] == ["table-missing"]
    tables = f"SELECT count(*) FROM duckdb_tables() WHERE database_name = '{ALIAS}' AND schema_name = '_meta'"
    assert query(path, data, tables) == [(0,)]


def test_a_column_not_in_the_catalog_is_an_error(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "sales" / "extra.yml").write_text(TABLE + "primary_key: [z]\ncolumns: [{name: y}]\n", encoding="utf-8")
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report) is None
    assert [f.code for f in report.findings] == ["column-missing", "column-missing"]


def test_refuses_a_folder_it_did_not_write(write, catalog, tmp_path):
    path, data = catalog
    root = project(write)
    out = tmp_path / "mine"
    out.mkdir()
    (out / "keep.txt").write_text("x")
    with pytest.raises(SpecError):
        load(Options(root, with_source=False), Target(str(path), data, out), Report())
    assert (out / "keep.txt").is_file()


def test_cli_needs_a_catalog(write, monkeypatch, capsys):
    monkeypatch.delenv("FDL_WORKING", raising=False)
    root = project(write)
    assert main(["load", "--root", str(root)]) == 2
    assert "FDL_WORKING" in capsys.readouterr().err


def test_cli_reads_the_catalog_from_the_environment(write, catalog, monkeypatch):
    path, data = catalog
    root = project(write)
    monkeypatch.setenv("FDL_WORKING", str(path))
    monkeypatch.setenv("FDL_DATA_PATH", data)
    assert main(["load", "--root", str(root), "--quiet"]) == 0
    assert query(path, data, f"SELECT title FROM {ALIAS}._meta.dataset") == [("Shop",)]
