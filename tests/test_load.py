from __future__ import annotations

import pytest
from conftest import fdl_run

from tabledoc import Options
from tabledoc import fdl as fdl_rows
from tabledoc.cli import main
from tabledoc.load import Target, load
from tabledoc.report import Report, SpecError

DATASET = "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\n"
TABLE = "$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json\n"


@pytest.fixture
def catalog(lake):
    """fdl's working metadata with sales.orders, sales.extra and the view sales.recent."""
    return str(
        lake(
            "CREATE SCHEMA lake.sales;"
            "CREATE TABLE lake.sales.orders AS SELECT 1 AS id, 'a' AS file;"
            "CREATE TABLE lake.sales.extra AS SELECT 1 AS x;"
            "CREATE VIEW lake.sales.recent AS SELECT * FROM lake.sales.orders"
        )
    )


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


def held(working, table, *columns):
    """The rows of ``_fdl.<table>`` (from fdl meta dump), as tuples of ``columns``, sorted."""
    return sorted(tuple(r.get(c) for c in columns) for r in fdl_rows.dump(working).get(table) or [])


def run(root, working, report=None, **target):
    return load(Options(root, with_source=False), Target(working, **target), report or Report())


def test_writes_fdl_and_the_folder_for_fdl_commit(write, catalog, tmp_path):
    root = project(write)
    out = tmp_path / "pack"
    report = Report()
    assert run(root, catalog, report, out=out, unlisted=True) is not None, report.render()
    assert held(catalog, "dataset", "title", "licenses") == [("Shop", [{"id": "CC-BY-4.0", "spdx": None, "url": None, "title": None}])]
    assert held(catalog, "tables", "name", "primary_key", "profile") == [
        ("extra", None, False),
        ("orders", ["id"], None),
        ("recent", None, None),
    ]
    assert held(catalog, "columns", "name", "asset") == [("file", True), ("id", None)]
    assert held(catalog, "files", "path", "media_type") == [
        ("README.md", "text/markdown"),
        ("sales/orders/README.md", "text/markdown"),
    ]
    assert held(catalog, "attributes", "table", "column", "key", "value") == [
        ("extra", "", "queria-published", False),
        ("orders", "id", "queria-entity", "order"),
    ]
    assert (out / "files" / "README.md").read_text() == "Overview.\n"
    assert (out / "files" / "sales" / "orders" / "README.md").read_text() == "Guide.\n"


def test_topics_and_keywords_are_queria_topics(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\ntitle: Shop\ntopics: [retail]\nqueria: {themes: [trade]}\n")
    (root / "sales" / "recent.yml").write_text(TABLE + "description: x\nkeywords: [latest]\n")
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    # queria: themes is no longer written.
    assert held(catalog, "attributes", "table", "key", "value") == [
        ("", "queria-topics", ["retail"]),
        ("orders", "queria-entity", "order"),
        ("recent", "queria-topics", ["latest"]),
    ]


def test_a_table_not_published_gets_no_profile(write, catalog):
    root = project(write)
    (root / "sales" / "recent.yml").write_text(TABLE + "description: The last orders.\nqueria: {published: false}\n")
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    assert held(catalog, "tables", "name", "profile") == [("orders", None), ("recent", False)]


def test_a_view_keeps_its_sql_in_the_metadata(write, catalog):
    root = project(write)
    (root / "sales" / "recent.yml").write_text(TABLE + "description: x\nsql: select 1\n")
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders\nsql: select 1 as id, 'a' as file\n")
    assert run(root, catalog) is not None
    assert held(catalog, "tables", "name", "sql") == [("orders", "select 1 as id, 'a' as file"), ("recent", None)]


def test_a_second_load_replaces_fdl(write, catalog):
    root = project(write)
    run(root, catalog)
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders\n", encoding="utf-8")
    assert run(root, catalog) is not None
    assert held(catalog, "columns", "name") == []


def test_keeps_the_sql_without_a_build(write, catalog):
    root = project(write)
    run(root, catalog)
    fdl_run("meta", "set", catalog, "sales.orders", "sql", "select 1")
    fdl_run("meta", "set", catalog, "sales.orders", "depends_on", "sales.extra")
    run(root, catalog)
    assert held(catalog, "tables", "name", "sql", "depends_on") == [
        ("orders", "select 1", ["sales.extra"]),
        ("recent", None, None),
    ]


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
    assert not any(fdl_rows.dump(catalog).values())


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
    monkeypatch.setenv("FDL_WORKING", catalog)
    assert main(["load", "--root", str(root), "--quiet"]) == 0
    assert held(catalog, "dataset", "title") == [("Shop",)]


def test_what_fdl_refuses_is_an_error(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(DATASET + "name: shop\nissued: 2026-10\n", encoding="utf-8")
    report = Report()
    assert run(root, catalog, report) is None
    assert [f.code for f in report.findings] == ["fdl"]
    assert "issued" in report.findings[0].message
    assert not any(fdl_rows.dump(catalog).values())


def test_names_match_without_regard_to_case(write, catalog):
    root = project(write)
    (root / "sales" / "Orders.yml").write_text(
        TABLE + "description: Upper.\nprimary_key: [ID]\ncolumns: [{name: ID, description: The order}]\n",
        encoding="utf-8",
    )
    (root / "sales" / "orders.yml").unlink()
    (root / "sales" / "orders.md").unlink()
    report = Report()
    assert run(root, catalog, report, unlisted=True) is not None, report.render()
    # Written as the working metadata spells them, which _fdl has to match.
    assert held(catalog, "tables", "name", "primary_key") == [("extra", None), ("orders", ["id"]), ("recent", None)]
    assert held(catalog, "columns", "name") == [("id",)]


def test_what_fdl_has_no_column_for_goes_to_attributes(write, catalog):
    root = project(write)
    (root / "tabledoc.yml").write_text(
        DATASET + "name: shop\nlicenses: [{id: x, url: https://x.example, commercial_use: true, share_alike: false}]\n"
    )
    (root / "sales" / "orders.yml").write_text(TABLE + "title: Orders\nsql: select 1\n")
    report = Report()
    assert run(root, catalog, report) is not None, report.render()
    assert held(catalog, "dataset", "licenses") == [([{"id": "x", "spdx": None, "url": "https://x.example", "title": None}],)]
    terms = [r["value"] for r in fdl_rows.dump(catalog)["attributes"] if r["key"] == "queria-license-terms"]
    assert terms == [{"x": {"commercial_use": True, "share_alike": False}}]


def test_dbt_keys_are_kept_without_a_build(write, catalog):
    root = project(write)
    run(root, catalog)
    fdl_run("meta", "set", catalog, "sales.orders", "dbt-materialized", '"table"')
    fdl_run("meta", "set", catalog, "sales.orders", "dbt-source-path", '"models/orders.sql"')
    run(root, catalog)
    dbt = [(r["key"], r["value"]) for r in fdl_rows.dump(catalog)["attributes"] if r["key"].startswith("dbt-")]
    assert sorted(dbt) == [("dbt-materialized", "table"), ("dbt-source-path", "models/orders.sql")]


def test_a_missing_manifest_is_info_when_dbt_built_before(write, catalog):
    root = project(write)
    write({"dbt_project.yml": "name: p\n"})
    run(root, catalog)
    fdl_run("meta", "set", catalog, "sales.orders", "dbt-source-path", '"m.sql"')
    report = Report()
    assert load(Options(root, with_source=False), Target(catalog), report, strict=True)
    assert [(f.level.value, f.code) for f in report.findings] == [("info", "manifest-missing")]
