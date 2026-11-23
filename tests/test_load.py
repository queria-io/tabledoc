from __future__ import annotations

import json

import pytest

from tabledoc import Options, tables
from tabledoc.cli import main
from tabledoc.load import ALIAS, Target, attached, data_path, load
from tabledoc.report import Report, SpecError

DATASET = "$schema: https://tabledoc.queria.io/schemas/dataset/v1.json\n"
TABLE = "$schema: https://tabledoc.queria.io/schemas/table/v1.json\n"


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
            + "name: shop\ntitle: Shop\ntitle_reading: ショップ\nlicenses: [CC-BY-4.0]\n",
            "README.md": "Overview.\n",
            "sales/orders.tabledoc.yml": TABLE
            + "title: Orders\ndescription: One row is one order.\nprimary_key: [id]\n"
            + "columns:\n  - {name: id, description: The order, entity: order}\n"
            + "  - {name: file, asset: true}\n",
            "sales/orders.md": "Guide.\n",
            "sales/recent.tabledoc.yml": TABLE + "description: The last orders.\n",
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


def test_writes_the_tables_and_the_folder_for_fdl_commit(write, catalog, tmp_path):
    root = project(write)
    out = tmp_path / "pack"
    report = Report()
    assert run(root, catalog, report, out=out, hide_undescribed=True) is not None, report.render()
    assert held(catalog, "dataset", "key", "value") == [("name", "shop")]
    assert held(catalog, "licenses", "id") == [("CC-BY-4.0",)]
    assert held(catalog, "table_licenses", "schema_name", "table_name", "license_id", "position") == [("", "", "CC-BY-4.0", 0)]
    assert held(catalog, "schemas", "schema_name") == [("sales",)]
    assert held(catalog, "tables", "table_name", "hidden") == [("extra", True), ("orders", False), ("recent", False)]
    assert held(catalog, "columns", "column_name", "entity") == [("id", "order")]
    assert held(catalog, "descriptions", "schema_name", "table_name", "column_name", "language", "title", "title_reading", "description") == [
        ("", "", "", "und", "Shop", "ショップ", None),
        ("sales", "orders", "", "und", "Orders", None, "One row is one order."),
        ("sales", "orders", "id", "und", None, None, "The order"),
        ("sales", "recent", "", "und", None, None, "The last orders."),
    ]
    assert held(catalog, "files", "path", "media_type") == [
        ("README.md", "text/markdown"),
        ("sales/orders/README.md", "text/markdown"),
    ]
    assert (out / "files" / "README.md").read_text() == "Overview.\n"
    assert (out / "files" / "sales" / "orders" / "README.md").read_text() == "Guide.\n"


def test_every_key_has_its_row(write, catalog):
    root = project(write)
    write(
        {
            "tabledoc.yml": DATASET
            + "name: shop\nlanguage: en\nissued: 2026-10-30\nhomepage: https://shop.example\nimage: cover.png\n"
            + "topics: [retail, trade]\nsynonyms: [store]\nspatial_coverage: [JP]\n"
            + "temporal_coverage: {start: 2020}\n"
            + "sources: [{id: site, title: Site, url: https://site.example}]\n"
            + "contributors: [{id: city, title: City, roles: [publisher, rightsHolder]}]\n",
            "cover.png": b"PNG",
            "sales/recent.tabledoc.yml": TABLE + "description: x\ntopics: [latest]\nhidden: true\nsources: [site]\n"
            + "columns: [{name: id, title_reading: アイディー, dimension: categorical}]\n"
            + "metrics: [{name: n, agg: count, expr: id, description: Orders}]\n",
        }
    )
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    assert held(catalog, "dataset", "key", "value") == [
        ("homepage", "https://shop.example"),
        ("image", "cover.png"),
        ("issued", "2026-10-30"),
        ("language", "en"),
        ("name", "shop"),
        ("temporal_start", "2020"),
    ]
    assert held(catalog, "topics", "table_name", "language", "topic") == [
        ("", "en", "retail"), ("", "en", "trade"), ("recent", "en", "latest"),
    ]
    assert held(catalog, "synonyms", "table_name", "synonym") == [("", "store")]
    assert held(catalog, "table_areas", "table_name", "area") == [("", "JP")]
    assert held(catalog, "sources", "id", "title", "url") == [("site", "Site", "https://site.example")]
    assert held(catalog, "table_sources", "table_name", "source_id") == [("", "site"), ("recent", "site")]
    assert held(catalog, "contributors", "id", "title", "position") == [("city", "City", 0)]
    assert held(catalog, "contributor_roles", "contributor_id", "role") == [("city", "publisher"), ("city", "rightsHolder")]
    assert held(catalog, "tables", "table_name", "hidden") == [("orders", False), ("recent", True)]
    assert held(catalog, "columns", "table_name", "column_name", "dimension") == [
        ("orders", "id", None), ("recent", "id", "categorical"),
    ]
    assert held(catalog, "metrics", "table_name", "metric_name", "agg", "expr", "description") == [
        ("recent", "n", "count", "id", "Orders"),
    ]
    assert ("cover.png",) in held(catalog, "files", "path")


def test_license_terms_are_columns_of_licenses(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(
        DATASET + "name: shop\nlicenses: [{id: x, url: https://x.example, commercial_use: true, share_alike: false}]\n"
    )
    (root / "sales" / "recent.tabledoc.yml").write_text(TABLE + "description: x\nlicenses: [x, CC0-1.0]\n")
    assert run(root, catalog) is not None
    assert held(catalog, "licenses", "id", "url", "commercial_use", "share_alike") == [
        ("CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/", True, False),
        ("x", "https://x.example", True, False),
    ]
    assert held(catalog, "table_licenses", "table_name", "license_id", "position") == [
        ("", "x", 0), ("recent", "CC0-1.0", 1), ("recent", "x", 0),
    ]


def test_an_id_defined_twice_differently_is_an_error(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\nsources: [{id: s, title: A}]\n")
    (root / "sales" / "recent.tabledoc.yml").write_text(TABLE + "sources: [{id: s, title: B}, gone]\n")
    report = Report()
    assert run(root, catalog, report) is None
    assert sorted(f.code for f in report.findings) == ["defined-twice", "undefined-id"]
    assert {f.source.name for f in report.findings} == {"recent.tabledoc.yml"}


def test_a_part_of_an_entry_refers_to_it(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\nsources: [{id: s, title: A, url: https://a.example}]\n")
    (root / "sales" / "recent.tabledoc.yml").write_text(TABLE + "sources: [{id: s, url: https://a.example}]\n")
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    assert held(catalog, "sources", "id", "title", "url") == [("s", "A", "https://a.example")]


def test_a_view_gets_no_sql(write, catalog):
    root = project(write)
    (root / "sales" / "recent.tabledoc.yml").write_text(TABLE + "description: x\nsql: select 1\ndepends_on: [sales.orders]\n")
    (root / "sales" / "orders.tabledoc.yml").write_text(TABLE + "title: Orders\nsql: select 1 as id, 'a' as file\n")
    assert run(root, catalog) is not None
    assert held(catalog, "tables", "table_name", "sql") == [
        ("orders", "select 1 as id, 'a' as file"),
        ("recent", None),
    ]
    assert held(catalog, "table_dependencies", "table_name") == []


def test_a_second_load_changes_only_what_differs(write, catalog):
    root = project(write)
    run(root, catalog)
    snapshots = "SELECT count(*) FROM lake.snapshots()"
    before = sql(catalog, snapshots)
    assert run(root, catalog) is not None
    # Nothing differs, so nothing is written.
    assert sql(catalog, snapshots) == before
    (root / "sales" / "orders.tabledoc.yml").write_text(TABLE + "title: Orders again\n", encoding="utf-8")
    assert run(root, catalog) is not None
    assert held(catalog, "descriptions", "table_name", "title") == [("", "Shop"), ("orders", "Orders again"), ("recent", None)]
    assert held(catalog, "columns", "column_name") == []


def test_keeps_the_sql_without_a_build(write, catalog):
    root = project(write)
    run(root, catalog)
    sql(catalog, "UPDATE lake._tabledoc.tables SET sql = 'select 1', "
        "source_path = 'models/orders.sql' WHERE table_name = 'orders'")
    sql(catalog, "INSERT INTO lake._tabledoc.table_dependencies VALUES ('sales', 'orders', 'sales.extra')")
    run(root, catalog)
    assert held(catalog, "tables", "table_name", "sql", "source_path") == [
        ("orders", "select 1", "models/orders.sql"),
        ("recent", None, None),
    ]
    assert held(catalog, "table_dependencies", "table_name", "depends_on") == [("orders", "sales.extra")]


def test_a_missing_manifest_is_info_when_dbt_built_before(write, catalog):
    root = project(write)
    write({"dbt_project.yml": "name: p\n"})
    run(root, catalog)
    sql(catalog, "UPDATE lake._tabledoc.tables SET source_path = 'm.sql' WHERE table_name = 'orders'")
    report = Report()
    assert load(Options(root, with_source=False), Target(*catalog), report, strict=True)
    assert [(f.level.value, f.code) for f in report.findings] == [("info", "manifest-missing")]


def test_writes_into_the_schema_it_is_told(write, catalog):
    root = project(write)
    assert run(root, catalog, schema="docs") is not None
    assert held(catalog, "descriptions", "table_name", "column_name", "title", schema="docs")[:1] == [("", "", "Shop")]
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\nschema: notes\ntitle: Notes\n")
    report = Report()
    assert run(root, catalog, report) is None
    assert "schema-violation" in [f.code for f in report.findings]


def test_a_schema_named_in_another_case_is_the_one_the_catalog_holds(write, catalog):
    root = project(write)
    assert run(root, catalog, schema="docs") is not None
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\ntitle: Again\n")
    assert run(root, catalog, schema="Docs") is not None
    assert held(catalog, "descriptions", "table_name", "column_name", "title", schema="docs")[:1] == [("", "", "Again")]


def test_an_asset_column_has_to_be_varchar(write, catalog):
    root = project(write)
    (root / "sales" / "extra.tabledoc.yml").write_text(TABLE + "columns: [{name: x, asset: true}]\n", encoding="utf-8")
    report = Report()
    assert run(root, catalog, report) is None
    assert [f.code for f in report.findings] == ["asset-type"]


def test_refuses_a_folder_inside_dot_fdl(write, catalog, tmp_path):
    root = project(write)
    with pytest.raises(SpecError, match=".fdl"):
        run(root, catalog, out=tmp_path / ".fdl" / "pack")


def test_a_table_not_in_the_catalog_writes_nothing(write, catalog):
    root = project(write)
    (root / "sales" / "gone.tabledoc.yml").write_text(TABLE + "title: Gone\n", encoding="utf-8")
    report = Report()
    assert run(root, catalog, report) is None
    assert [f.code for f in report.findings] == ["table-missing"]
    assert sql(catalog, "SELECT count(*) FROM duckdb_schemas() WHERE schema_name = '_tabledoc'") == [(0,)]


def test_a_column_not_in_the_catalog_is_an_error(write, catalog):
    root = project(write)
    (root / "sales" / "extra.tabledoc.yml").write_text(TABLE + "primary_key: [z]\ncolumns: [{name: y}]\n", encoding="utf-8")
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
    assert held(catalog, "descriptions", "table_name", "column_name", "title")[:1] == [("", "", "Shop")]


def test_text_in_more_than_one_language_is_a_row_for_each(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(
        DATASET
        + "name: shop\nlanguage: ja\ntitle: {ja: 店, en: Shop}\ntopics: {ja: [小売], en: [retail]}\n"
        + "homepage: {ja: https://example.jp, en: https://example.com}\n"
    )
    (root / "sales" / "orders.tabledoc.yml").write_text(
        TABLE + "title: 注文\ncolumns: [{name: id, title: {ja: ID, en: Order ID}}]\n", encoding="utf-8"
    )
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    assert held(catalog, "descriptions", "table_name", "column_name", "language", "title") == [
        ("", "", "en", "Shop"),
        ("", "", "ja", "店"),
        ("orders", "", "ja", "注文"),
        ("orders", "id", "en", "Order ID"),
        ("orders", "id", "ja", "ID"),
        ("recent", "", "ja", None),
    ]
    assert held(catalog, "topics", "language", "topic") == [("en", "retail"), ("ja", "小売")]
    assert held(catalog, "dataset", "key", "value") == [("homepage", "https://example.jp"), ("language", "ja"), ("name", "shop")]
    assert [f.code for f in report.findings] == ["one-language"]


def test_a_value_the_table_cannot_hold_is_an_error(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\nissued: 2026-10\n", encoding="utf-8")
    report = Report()
    assert run(root, catalog, report) is None
    assert [f.message for f in report.findings if f.code == "value-type"] == [
        "_tabledoc.dataset issued: value cannot be written as DATE",
    ]


def test_names_are_written_as_the_catalog_spells_them(write, catalog):
    root = project(write)
    (root / "sales" / "Orders.tabledoc.yml").write_text(
        TABLE + "description: Upper.\nprimary_key: [ID]\ncolumns: [{name: ID, description: The order}]\n",
        encoding="utf-8",
    )
    (root / "sales" / "orders.tabledoc.yml").unlink()
    (root / "sales" / "orders.md").unlink()
    report = Report()
    assert run(root, catalog, report, hide_undescribed=True) is not None, report.render()
    assert held(catalog, "tables", "table_name") == [("extra",), ("orders",), ("recent",)]
    assert held(catalog, "columns", "column_name") == [("id",)]


def test_data_path_follows_fdl_status(tmp_path, monkeypatch):
    working = tmp_path / "work.sqlite"
    assert data_path(str(working), None) is None
    (tmp_path / "work.sqlite.fdl").mkdir()
    calls = []

    def call(args):
        calls.append(args)
        return json.dumps({"remote": "https://data.example/d/", "base": None, "data_path": "s3://bucket/repo/data/"})

    monkeypatch.setattr("tabledoc.fdl_state.call", call)
    assert data_path("ducklake:" + str(working), None) == "s3://bucket/repo/data/"
    assert calls == [["status", str(working), "--json"]]
    assert data_path(str(working), "given/") == "given/"


def test_an_fdl_whose_status_gives_no_data_path_is_an_error(tmp_path, monkeypatch):
    working = tmp_path / "work.sqlite"
    (tmp_path / "work.sqlite.fdl").mkdir()
    monkeypatch.setattr("tabledoc.fdl_state.call", lambda args: json.dumps({"pending": None}))
    with pytest.raises(SpecError, match="0.35"):
        data_path(str(working), None)


def test_a_missing_manifest_stays_a_warning_when_a_table_dbt_built_is_not_described(write, catalog):
    root = project(write)
    write({"dbt_project.yml": "name: p\n"})
    run(root, catalog, hide_undescribed=True)
    sql(catalog, "UPDATE lake._tabledoc.tables SET source_path = 'm.sql' WHERE table_name = 'extra'")
    report = Report()
    assert load(Options(root, with_source=False), Target(*catalog), report, strict=True) is None
    assert [(f.level.value, f.code) for f in report.findings] == [("warning", "manifest-missing")]


def test_unlisted_leaves_out_the_schemas_of_a_description(write, catalog):
    root = project(write)
    assert run(root, catalog, schema="docs") is not None
    assert run(root, catalog, hide_undescribed=True) is not None
    assert held(catalog, "tables", "schema_name", "table_name") == [("sales", "extra"), ("sales", "orders"), ("sales", "recent")]


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
            "sales/orders.tabledoc.yml": TABLE + "description: One row is one order.\n",
            "dbt_project.yml": "name: p\n",
            "target/manifest.json": json.dumps({"nodes": nodes}),
        }
    )
    report = Report()
    assert run(root, catalog, report, hide_undescribed=True) is not None, report.render()
    assert held(catalog, "tables", "table_name", "hidden", "sql") == [
        ("extra", True, "select 1 as x"),
        ("orders", False, "select 1 as x"),
        ("recent", True, None),
    ]
    # Without a build, each keeps its SQL, and the missing manifest is only worth knowing.
    (root / "target" / "manifest.json").unlink()
    report = Report()
    assert run(root, catalog, report, hide_undescribed=True) is not None, report.render()
    assert [(f.level.value, f.code) for f in report.findings] == [("info", "manifest-missing")]
    assert held(catalog, "tables", "table_name", "hidden", "sql") == [
        ("extra", True, "select 1 as x"),
        ("orders", False, "select 1 as x"),
        ("recent", True, None),
    ]


def test_drops_a_column_an_earlier_tabledoc_wrote(write, catalog):
    root = project(write)
    run(root, catalog)
    sql(catalog, "ALTER TABLE lake._tabledoc.tables ADD COLUMN materialized VARCHAR")
    run(root, catalog)
    found = sql(catalog, "SELECT column_name FROM duckdb_columns() WHERE schema_name = '_tabledoc' AND table_name = 'tables'")
    assert ("materialized",) not in found


def test_repository_comes_from_git_and_source_path_from_its_root(write, catalog):
    import subprocess

    nodes = {
        "model.p.extra": {
            "resource_type": "model",
            "name": "extra",
            "schema": "sales",
            "alias": "extra",
            "original_file_path": "models/extra.sql",
            "config": {"materialized": "table", "enabled": True, "meta": {}},
            "compiled_code": "select 1 as x",
            "columns": {},
            "description": "",
        }
    }
    top = write({"ds/tabledoc.yml": DATASET + "name: shop\n", "ds/dbt_project.yml": "name: p\n",
                 "ds/target/manifest.json": json.dumps({"nodes": nodes})})
    for args in (["init", "-q"], ["remote", "add", "origin", "git@github.com:example/shop.git"]):
        subprocess.run(["git", "-C", str(top), *args], check=True)
    subprocess.run(["git", "-C", str(top), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    load(Options(top / "ds"), Target(*catalog), Report())
    assert held(catalog, "dataset", "key", "value")[-1] == ("repository", "https://github.com/example/shop")
    assert held(catalog, "tables", "table_name", "source_path") == [("extra", "ds/models/extra.sql")]


def test_sends_fdl_token_to_the_remote_of_a_working_metadata(tmp_path, monkeypatch):
    from tabledoc.load import remote_secret

    catalog = tmp_path / "work.sqlite"
    monkeypatch.setenv("FDL_TOKEN", "t'k")
    assert remote_secret(str(catalog)) is None
    (tmp_path / "work.sqlite.fdl").mkdir()
    status = {"remote": "https://data.example/d/", "base": None, "data_path": "/tmp/d/"}
    monkeypatch.setattr("tabledoc.fdl_state.call", lambda args: json.dumps(status))
    assert remote_secret(str(catalog)) == (
        "CREATE SECRET tabledoc_remote (TYPE http, BEARER_TOKEN 't''k', SCOPE 'https://data.example/d/')"
    )
    monkeypatch.delenv("FDL_TOKEN")
    assert remote_secret(str(catalog)) is None


def test_unlisted_leaves_out_a_description_an_earlier_tabledoc_wrote(write, catalog):
    root = project(write)
    sql(catalog, "CREATE SCHEMA lake._queria; CREATE TABLE lake._queria.dataset (id VARCHAR);"
        "CREATE TABLE lake._queria.schemas (schema VARCHAR); CREATE TABLE lake._queria.tables (schema VARCHAR);"
        "CREATE TABLE lake._queria.columns (schema VARCHAR); CREATE TABLE lake._queria.files (path VARCHAR)")
    assert run(root, catalog, hide_undescribed=True) is not None
    assert held(catalog, "tables", "schema_name", "table_name") == [("sales", "extra"), ("sales", "orders"), ("sales", "recent")]


def test_replaces_the_tables_of_an_earlier_tabledoc(write, catalog):
    root = project(write)
    sql(catalog, "CREATE SCHEMA lake._tabledoc;"
        "CREATE TABLE lake._tabledoc.tables (schema VARCHAR, name VARCHAR, published BOOLEAN);"
        "INSERT INTO lake._tabledoc.tables VALUES ('sales', 'orders', false);"
        "CREATE TABLE lake._tabledoc.texts (schema VARCHAR, title VARCHAR);"
        "CREATE TABLE lake._tabledoc.table_profiles (schema_name VARCHAR, table_name VARCHAR, rows BIGINT)")
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    assert held(catalog, "tables", "table_name", "hidden") == [("orders", False), ("recent", False)]
    found = sql(catalog, "SELECT table_name FROM duckdb_tables() WHERE schema_name = '_tabledoc' ORDER BY 1")
    assert ("texts",) not in found
    assert ("table_profiles",) in found


def test_keeps_the_other_tables_of_the_schema_written_into(write, catalog):
    root = project(write)
    sql(catalog, "CREATE SCHEMA lake.docs; CREATE TABLE lake.docs.notes AS SELECT 1 AS x")
    report = Report()
    assert run(root, catalog, report, schema="docs") is not None, report.render()
    assert sql(catalog, "SELECT count(*) FROM lake.docs.notes") == [(1,)]


def test_the_primary_key_is_the_key_position_of_its_columns(write, lake):
    catalog = lake("CREATE SCHEMA lake.s; CREATE TABLE lake.s.t AS SELECT 1 AS a, 2 AS b, 3 AS c")
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "s/t.tabledoc.yml": TABLE + "primary_key: [b, a]\ncolumns:\n  - {name: a, title: A}\n  - {name: c, title: C}\n",
        }
    )
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    assert held(catalog, "columns", "column_name", "key_position") == [("a", 1), ("b", 0), ("c", None)]
