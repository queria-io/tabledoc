from __future__ import annotations

import json

import pytest

from tabledoc import Options
from tabledoc.cli import main
from tabledoc.load import ALIAS, Target, attached, data_path, load
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


def test_writes_fdl_and_the_folder_for_fdl_commit(write, catalog, tmp_path):
    path, data = catalog
    root = project(write)
    out = tmp_path / "pack"
    report = Report()
    found = load(Options(root, with_source=False), Target(str(path), data, out, unlisted=True), report)
    assert found is not None, report.render()
    assert query(path, data, f"SELECT title, licenses[1].id FROM {ALIAS}._fdl.dataset") == [("Shop", "CC-BY-4.0")]
    assert query(path, data, f"SELECT schema, name, primary_key, profile FROM {ALIAS}._fdl.tables ORDER BY name") == [
        ("sales", "extra", None, False),
        ("sales", "orders", ["id"], None),
        ("sales", "recent", None, None),
    ]
    assert query(path, data, f"SELECT name, asset FROM {ALIAS}._fdl.columns ORDER BY name") == [
        ("file", True),
        ("id", None),
    ]
    assert query(path, data, f"SELECT path, media_type FROM {ALIAS}._fdl.files ORDER BY path") == [
        ("README.md", "text/markdown"),
        ("sales/orders/README.md", "text/markdown"),
    ]
    assert query(path, data, f'SELECT schema, "table", key, value FROM {ALIAS}._fdl.attributes ORDER BY ALL') == [
        ("sales", "extra", "queria-published", "false"),
        ("sales", "orders", "queria-entity", '"order"'),
    ]
    # load writes no comments: _fdl is where the description is.
    comments = f"SELECT comment FROM duckdb_tables() WHERE database_name = '{ALIAS}' AND table_name = 'orders'"
    assert query(path, data, comments) == [(None,)]
    assert (out / "files" / "README.md").read_text() == "Overview.\n"
    assert (out / "files" / "sales" / "orders" / "README.md").read_text() == "Guide.\n"
    assert not (out / "dataset.json").exists()


def test_topics_and_keywords_are_queria_topics(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\ntitle: Shop\ntopics: [retail]\nqueria: {themes: [trade]}\n")
    (root / "sales" / "recent.yml").write_text(TABLE + "description: x\nkeywords: [latest]\n")
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report) is not None, report.render()
    # queria: themes is no longer written.
    topics = f"SELECT \"table\", key, value FROM {ALIAS}._fdl.attributes WHERE key = 'queria-topics' ORDER BY ALL"
    assert query(path, data, topics) == [
        ("", "queria-topics", '["retail"]'),
        ("recent", "queria-topics", '["latest"]'),
    ]


def test_a_table_not_published_gets_no_profile(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "sales" / "recent.yml").write_text(TABLE + "description: The last orders.\nqueria: {published: false}\n")
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report) is not None, report.render()
    assert query(path, data, f"SELECT name, profile FROM {ALIAS}._fdl.tables ORDER BY name") == [
        ("orders", None),
        ("recent", False),
    ]


def test_a_view_keeps_its_sql_in_the_metadata(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "sales" / "recent.yml").write_text(TABLE + "description: x\nsql: select 1\n")
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders\nsql: select 1 as id, 'a' as file\n")
    assert load(Options(root, with_source=False), Target(str(path), data), Report()) is not None
    assert query(path, data, f"SELECT name, sql FROM {ALIAS}._fdl.tables ORDER BY name") == [
        ("orders", "select 1 as id, 'a' as file"),
        ("recent", None),
    ]


def test_drops_the_meta_schema_of_tabledoc_0_3(write, catalog):
    path, data = catalog
    root = project(write)
    with attached(str(path), data) as con:
        con.execute(f"CREATE SCHEMA {ALIAS}._meta")
        con.execute(f"CREATE TABLE {ALIAS}._meta.tables AS SELECT 'sales' AS schema, 'orders' AS name, "
                    "'select 2' AS sql, ['sales.extra'] AS depends_on")
    assert load(Options(root, with_source=False), Target(str(path), data), Report()) is not None
    schemas = f"SELECT schema_name FROM duckdb_schemas() WHERE database_name = '{ALIAS}' ORDER BY 1"
    assert ("_meta",) not in query(path, data, schemas)
    # What _meta held of the build stays, as without a build it would from _fdl.
    assert query(path, data, f"SELECT sql, depends_on FROM {ALIAS}._fdl.tables WHERE name = 'orders'") == [
        ("select 2", ["sales.extra"])
    ]


def test_a_second_load_replaces_fdl(write, catalog):
    path, data = catalog
    root = project(write)
    load(Options(root, with_source=False), Target(str(path), data), Report())
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders\n", encoding="utf-8")
    assert load(Options(root, with_source=False), Target(str(path), data), Report()) is not None
    assert query(path, data, f"SELECT count(*) FROM {ALIAS}._fdl.columns") == [(0,)]


def test_keeps_the_sql_without_a_build(write, catalog):
    path, data = catalog
    root = project(write)
    load(Options(root, with_source=False), Target(str(path), data), Report())
    with attached(str(path), data) as con:
        con.execute(f"UPDATE {ALIAS}._fdl.tables SET sql = 'select 1', depends_on = ['sales.extra'] WHERE name = 'orders'")
    load(Options(root, with_source=False), Target(str(path), data), Report())
    assert query(path, data, f"SELECT sql, depends_on FROM {ALIAS}._fdl.tables WHERE name = 'orders'") == [
        ("select 1", ["sales.extra"])
    ]


def test_an_asset_column_has_to_be_varchar(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "sales" / "extra.yml").write_text(TABLE + "columns: [{name: x, asset: true}]\n", encoding="utf-8")
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report) is None
    assert [f.code for f in report.findings] == ["asset-type"]


def test_refuses_a_folder_inside_dot_fdl(write, catalog, tmp_path):
    path, data = catalog
    root = project(write)
    with pytest.raises(SpecError, match=".fdl"):
        load(Options(root, with_source=False), Target(str(path), data, tmp_path / ".fdl" / "pack"), Report())


def test_a_table_not_in_the_catalog_writes_nothing(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "sales" / "gone.yml").write_text(TABLE + "title: Gone\n", encoding="utf-8")
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report) is None
    assert [f.code for f in report.findings] == ["table-missing"]
    tables = f"SELECT count(*) FROM duckdb_tables() WHERE database_name = '{ALIAS}' AND schema_name = '_fdl'"
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
    assert query(path, data, f"SELECT title FROM {ALIAS}._fdl.dataset") == [("Shop",)]


def test_a_value_fdl_cannot_hold_is_an_error(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "tabledoc.yml").write_text(
        DATASET + "name: shop\nissued: 2026-10\n", encoding="utf-8"
    )
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report) is None
    assert sorted(f.message for f in report.findings if f.code == "fdl-type") == [
        "_fdl.dataset: issued cannot be written as DATE",
    ]


def test_names_match_without_regard_to_case(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "sales" / "Orders.yml").write_text(
        TABLE + "description: Upper.\nprimary_key: [ID]\ncolumns: [{name: ID, description: The order}]\n",
        encoding="utf-8",
    )
    (root / "sales" / "orders.yml").unlink()
    (root / "sales" / "orders.md").unlink()
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data, unlisted=True), report) is not None, (
        report.render()
    )
    assert query(path, data, f"SELECT name FROM {ALIAS}._fdl.tables ORDER BY name") == [
        ("Orders",),
        ("extra",),
        ("recent",),
    ]


def test_a_quote_in_the_path(write, tmp_path):
    folder = tmp_path / "it's"
    (folder / "data").mkdir(parents=True)
    with attached(str(folder / "w.sqlite"), (folder / "data").as_posix() + "/") as con:
        con.execute(f"CREATE TABLE {ALIAS}.main.t AS SELECT 1 AS x")


def test_data_path_follows_fdl_clones_note(tmp_path):
    working = tmp_path / "work.sqlite"
    note = tmp_path / "work.sqlite.fdl.json"
    note.write_text(json.dumps({"storage": "s3://bucket/repo/", "data_dir": "data/"}))
    assert data_path(str(working), None) == "s3://bucket/repo/data/"
    assert data_path("ducklake:" + str(working), None) == "s3://bucket/repo/data/"
    note.write_text(json.dumps({"data": str(tmp_path / "d")}))
    assert data_path(str(working), None) == (tmp_path / "d").resolve().as_posix() + "/"
    assert data_path(str(working), "given/") == "given/"


def test_what_fdl_has_no_column_for_goes_to_attributes(write, catalog):
    path, data = catalog
    root = project(write)
    (root / "tabledoc.yml").write_text(
        DATASET + "name: shop\nlicenses: [{id: x, url: https://x.example, commercial_use: true, share_alike: false}]\n"
    )
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders\nsql: select 1\n")
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report) is not None, report.render()
    assert query(path, data, f"SELECT licenses FROM {ALIAS}._fdl.dataset") == [
        ([{"id": "x", "spdx": None, "url": "https://x.example", "title": None}],)
    ]
    terms = f"SELECT value FROM {ALIAS}._fdl.attributes WHERE key = 'queria-license-terms'"
    assert [json.loads(v) for (v,) in query(path, data, terms)] == [{"x": {"commercial_use": True, "share_alike": False}}]


def test_dbt_keys_are_kept_without_a_build(write, catalog):
    path, data = catalog
    root = project(write)
    load(Options(root, with_source=False), Target(str(path), data), Report())
    with attached(str(path), data) as con:
        con.execute(
            f"INSERT INTO {ALIAS}._fdl.attributes VALUES ('sales', 'orders', '', 'dbt-materialized', '\"table\"'), "
            "('sales', 'orders', '', 'dbt-source-path', '\"models/orders.sql\"')"
        )
    load(Options(root, with_source=False), Target(str(path), data), Report())
    dbt = f"SELECT key, value FROM {ALIAS}._fdl.attributes WHERE key LIKE 'dbt-%' ORDER BY key"
    assert query(path, data, dbt) == [("dbt-materialized", '"table"'), ("dbt-source-path", '"models/orders.sql"')]


def test_a_missing_manifest_is_info_when_dbt_built_before(write, catalog):
    path, data = catalog
    root = project(write)
    write({"dbt_project.yml": "name: p\n"})
    load(Options(root, with_source=False), Target(str(path), data), Report())
    with attached(str(path), data) as con:
        con.execute(f"INSERT INTO {ALIAS}._fdl.attributes VALUES ('sales', 'orders', '', 'dbt-source-path', '\"m.sql\"')")
    report = Report()
    assert load(Options(root, with_source=False), Target(str(path), data), report, strict=True)
    assert [(f.level.value, f.code) for f in report.findings] == [("info", "manifest-missing")]
