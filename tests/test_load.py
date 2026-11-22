from __future__ import annotations

import json

import pytest

from tabledoc import Options, tables
from tabledoc.cli import main
from tabledoc.load import ALIAS, Target, attached, data_path, load
from tabledoc.report import Report, SpecError

DATASET = "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\n"
TABLE = "$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json\n"


@pytest.fixture
def catalog(lake):
    """A DuckLake catalog with sales.orders, sales.extra and the view sales.recent."""
    return lake(
        "CREATE SCHEMA lake.sales;"
        "CREATE TABLE lake.sales.orders AS SELECT 1 AS id, 'a' AS file;"
        "CREATE TABLE lake.sales.extra AS SELECT 1 AS x;"
        "CREATE VIEW lake.sales.recent AS SELECT * FROM lake.sales.orders"
    )


def project(write):
    return write(
        {
            "tabledoc.yml": DATASET
            + "name: shop\ntitle: Shop\nlicenses: [CC-BY-4.0]\nqueria: {themes: [trade], title_kana: ショップ}\n",
            "README.md": "Overview.\n",
            "sales/orders.yml": TABLE
            + "title: Orders\ndescription: One row is one order.\nprimary_key: [id]\n"
            + "columns:\n  - {name: id, description: The order, entity: {type: primary, name: order}}\n"
            + "  - {name: file, asset: true}\n",
            "sales/orders.md": "Guide.\n",
            "sales/recent.yml": TABLE + "description: The last orders.\n",
        }
    )


def held(catalog, table, *columns, schema=tables.SCHEMA):
    """The rows of ``<schema>.<table>``, as tuples of ``columns``, sorted."""
    with attached(*catalog) as con:
        found = tables.read(con, ALIAS, schema).get(table) or []
    return sorted(tuple(r.get(c) for c in columns) for r in found)


def run(root, catalog, report=None, **target):
    return load(Options(root, with_source=False), Target(*catalog, **target), report or Report())


def sql(catalog, statement):
    with attached(*catalog) as con:
        return con.execute(statement).fetchall()


def test_writes_queria_and_the_folder_for_fdl_commit(write, catalog, tmp_path):
    root = project(write)
    out = tmp_path / "pack"
    report = Report()
    assert run(root, catalog, report, out=out, unlisted=True) is not None, report.render()
    assert held(catalog, "dataset", "id", "title", "title_kana", "licenses") == [
        ("dataset", "Shop", "ショップ", [{"id": "CC-BY-4.0"}])
    ]
    assert held(catalog, "tables", "name", "title", "published") == [
        ("extra", None, False),
        ("orders", "Orders", None),
        ("recent", None, None),
    ]
    assert held(catalog, "columns", "name", "description", "entity") == [("id", "The order", "order")]
    assert held(catalog, "files", "path", "media_type") == [
        ("README.md", "text/markdown"),
        ("sales/orders/README.md", "text/markdown"),
    ]
    assert (out / "files" / "README.md").read_text() == "Overview.\n"
    assert (out / "files" / "sales" / "orders" / "README.md").read_text() == "Guide.\n"


def test_queria_keys_are_columns(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(
        DATASET + "name: shop\ntopics: [retail]\nqueria: {cover: cover.png, ai_context: {hint: x}}\n"
    )
    (root / "sales" / "recent.yml").write_text(TABLE + "description: x\nkeywords: [latest]\nqueria: {published: false}\n")
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    assert held(catalog, "dataset", "topics", "cover", "ai_context") == [(["retail"], "cover.png", {"hint": "x"})]
    assert held(catalog, "tables", "name", "topics", "published") == [("orders", None, None), ("recent", ["latest"], False)]


def test_license_terms_stay_in_licenses(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(
        DATASET + "name: shop\nlicenses: [{id: x, url: https://x.example, commercial_use: true, share_alike: false}]\n"
    )
    assert run(root, catalog) is not None
    assert held(catalog, "dataset", "licenses") == [
        ([{"id": "x", "url": "https://x.example", "commercial_use": True, "share_alike": False}],)
    ]


def test_a_view_gets_no_sql(write, catalog):
    root = project(write)
    (root / "sales" / "recent.yml").write_text(TABLE + "description: x\nsql: select 1\ndepends_on: [sales.orders]\n")
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders\nsql: select 1 as id, 'a' as file\n")
    assert run(root, catalog) is not None
    assert held(catalog, "tables", "name", "sql", "depends_on") == [
        ("orders", "select 1 as id, 'a' as file", None),
        ("recent", None, None),
    ]


def test_a_second_load_changes_only_what_differs(write, catalog):
    root = project(write)
    run(root, catalog)
    snapshots = "SELECT count(*) FROM lake.snapshots()"
    before = sql(catalog, snapshots)
    assert run(root, catalog) is not None
    # Nothing differs, so nothing is written.
    assert sql(catalog, snapshots) == before
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders again\n", encoding="utf-8")
    assert run(root, catalog) is not None
    assert held(catalog, "tables", "name", "title") == [("orders", "Orders again"), ("recent", None)]
    assert held(catalog, "columns", "name") == []


def test_keeps_the_sql_without_a_build(write, catalog):
    root = project(write)
    run(root, catalog)
    sql(catalog, "UPDATE lake._tabledoc.tables SET sql = 'select 1', depends_on = ['sales.extra'], "
        "source_path = 'models/orders.sql' WHERE name = 'orders'")
    run(root, catalog)
    assert held(catalog, "tables", "name", "sql", "depends_on", "source_path") == [
        ("orders", "select 1", ["sales.extra"], "models/orders.sql"),
        ("recent", None, None, None),
    ]


def test_a_missing_manifest_is_info_when_dbt_built_before(write, catalog):
    root = project(write)
    write({"dbt_project.yml": "name: p\n"})
    run(root, catalog)
    sql(catalog, "UPDATE lake._tabledoc.tables SET source_path = 'm.sql' WHERE name = 'orders'")
    report = Report()
    assert load(Options(root, with_source=False), Target(*catalog), report, strict=True)
    assert [(f.level.value, f.code) for f in report.findings] == [("info", "manifest-missing")]


def test_writes_into_the_schema_it_is_told(write, catalog):
    root = project(write)
    assert run(root, catalog, schema="docs") is not None
    assert held(catalog, "dataset", "title", schema="docs") == [("Shop",)]
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\nschema: notes\ntitle: Notes\n")
    assert run(root, catalog) is not None
    assert held(catalog, "dataset", "title", schema="notes") == [("Notes",)]


def test_an_asset_column_has_to_be_varchar(write, catalog):
    root = project(write)
    (root / "sales" / "extra.yml").write_text(TABLE + "columns: [{name: x, asset: true}]\n", encoding="utf-8")
    report = Report()
    assert run(root, catalog, report) is None
    assert [f.code for f in report.findings] == ["asset-type"]


def test_refuses_a_folder_inside_dot_fdl(write, catalog, tmp_path):
    root = project(write)
    with pytest.raises(SpecError, match=".fdl"):
        run(root, catalog, out=tmp_path / ".fdl" / "pack")


def test_a_table_not_in_the_catalog_writes_nothing(write, catalog):
    root = project(write)
    (root / "sales" / "gone.yml").write_text(TABLE + "title: Gone\n", encoding="utf-8")
    report = Report()
    assert run(root, catalog, report) is None
    assert [f.code for f in report.findings] == ["table-missing"]
    assert sql(catalog, "SELECT count(*) FROM duckdb_schemas() WHERE schema_name = '_tabledoc'") == [(0,)]


def test_a_column_not_in_the_catalog_is_an_error(write, catalog):
    root = project(write)
    (root / "sales" / "extra.yml").write_text(TABLE + "primary_key: [z]\ncolumns: [{name: y}]\n", encoding="utf-8")
    report = Report()
    assert run(root, catalog, report) is None
    assert [f.code for f in report.findings] == ["column-missing", "column-missing"]


def test_refuses_a_folder_it_did_not_write(write, catalog, tmp_path):
    root = project(write)
    out = tmp_path / "mine"
    out.mkdir()
    (out / "keep.txt").write_text("x")
    with pytest.raises(SpecError):
        run(root, catalog, out=out)
    assert (out / "keep.txt").is_file()


def test_cli_needs_a_catalog(write, monkeypatch, capsys):
    monkeypatch.delenv("FDL_WORKING", raising=False)
    root = project(write)
    assert main(["load", "--root", str(root)]) == 2
    assert "FDL_WORKING" in capsys.readouterr().err


def test_cli_reads_the_catalog_from_the_environment(write, catalog, monkeypatch):
    root = project(write)
    monkeypatch.setenv("FDL_WORKING", catalog[0])
    monkeypatch.setenv("FDL_DATA_PATH", catalog[1])
    assert main(["load", "--root", str(root), "--quiet"]) == 0
    assert held(catalog, "dataset", "title") == [("Shop",)]


def test_a_value_the_table_cannot_hold_is_an_error(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\nissued: 2026-10\n", encoding="utf-8")
    report = Report()
    assert run(root, catalog, report) is None
    assert [f.message for f in report.findings if f.code == "value-type"] == [
        "_tabledoc.dataset: issued cannot be written as DATE",
    ]


def test_names_are_written_as_the_catalog_spells_them(write, catalog):
    root = project(write)
    (root / "sales" / "Orders.yml").write_text(
        TABLE + "description: Upper.\nprimary_key: [ID]\ncolumns: [{name: ID, description: The order}]\n",
        encoding="utf-8",
    )
    (root / "sales" / "orders.yml").unlink()
    (root / "sales" / "orders.md").unlink()
    report = Report()
    assert run(root, catalog, report, unlisted=True) is not None, report.render()
    assert held(catalog, "tables", "name") == [("extra",), ("orders",), ("recent",)]
    assert held(catalog, "columns", "name") == [("id",)]


def test_data_path_follows_fdl_clones_note(tmp_path):
    working = tmp_path / "work.sqlite"
    note = tmp_path / "work.sqlite.fdl.json"
    note.write_text(json.dumps({"storage": "s3://bucket/repo/", "data_dir": "data/"}))
    assert data_path(str(working), None) == "s3://bucket/repo/data/"
    assert data_path("ducklake:" + str(working), None) == "s3://bucket/repo/data/"
    note.write_text(json.dumps({"data": str(tmp_path / "d")}))
    assert data_path(str(working), None) == (tmp_path / "d").resolve().as_posix() + "/"
    assert data_path(str(working), "given/") == "given/"


def test_a_missing_manifest_stays_a_warning_when_a_table_dbt_built_is_not_described(write, catalog):
    root = project(write)
    write({"dbt_project.yml": "name: p\n"})
    run(root, catalog, unlisted=True)
    sql(catalog, "UPDATE lake._tabledoc.tables SET source_path = 'm.sql' WHERE name = 'extra'")
    report = Report()
    assert load(Options(root, with_source=False), Target(*catalog), report, strict=True) is None
    assert [(f.level.value, f.code) for f in report.findings] == [("warning", "manifest-missing")]


def test_unlisted_leaves_out_the_schemas_of_a_description(write, catalog):
    root = project(write)
    assert run(root, catalog, schema="_queria") is not None
    assert run(root, catalog, unlisted=True) is not None
    assert held(catalog, "tables", "schema", "name") == [("sales", "extra"), ("sales", "orders"), ("sales", "recent")]


def test_unlisted_covers_a_table_dbt_built_that_says_only_its_sql(write, catalog):
    nodes = {
        f"model.p.{name}": {
            "resource_type": "model",
            "name": name,
            "schema": "sales",
            "alias": name,
            "original_file_path": f"models/{name}.sql",
            "config": {"materialized": "table", "enabled": True, "meta": {}},
            "compiled_code": "select 1 as x",
            "columns": {},
            "description": "",
        }
        for name in ("extra", "orders")
    }
    root = write(
        {
            "tabledoc.yml": DATASET + "name: shop\n",
            "sales/orders.yml": TABLE + "description: One row is one order.\n",
            "dbt_project.yml": "name: p\n",
            "target/manifest.json": json.dumps({"nodes": nodes}),
        }
    )
    report = Report()
    assert run(root, catalog, report, unlisted=True) is not None, report.render()
    assert held(catalog, "tables", "name", "published", "sql") == [
        ("extra", False, "select 1 as x"),
        ("orders", None, "select 1 as x"),
        ("recent", False, None),
    ]
