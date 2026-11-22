from __future__ import annotations

import json

import pytest

from tabledoc import Options, tables
from tabledoc.cli import main
from tabledoc.dump import Source, dump
from tabledoc.load import ALIAS, Target, attached, load
from tabledoc.report import Report, SpecError

DATASET = "$schema: https://tabledoc.queria.io/schemas/dataset/v1.json\n"
TABLE = "$schema: https://tabledoc.queria.io/schemas/table/v1.json\n"


@pytest.fixture
def loaded(write, lake, tmp_path):
    """A catalog loaded from a description, and the folder of its files by sha256."""
    catalog = lake(
        "CREATE SCHEMA lake.sales;"
        "CREATE TABLE lake.sales.orders AS SELECT 1 AS id, 'a' AS file;"
        "CREATE TABLE lake.sales.extra AS SELECT 1 AS x"
    )
    root = write(
        {
            "src/tabledoc.yml": DATASET
            + "name: shop\ntitle: Shop\ndescription: |-\n  Two\n  lines\nlicenses: [CC-BY-4.0, {id: own, commercial_use: false}]\nissued: 2026-10-30\n"
            + "schemas: [{name: sales, title: Sales}]\ndocuments: [docs/method.md]\n"
            + "topics: [trade]\ntitle_reading: ショップ\nimage: docs/chart.png\nspatial_coverage: [JP]\n"
            + "sources: [{id: site, title: Site}]\ncontributors: [{id: me, title: Me, roles: [publisher]}]\n",
            "src/README.md": "Overview. ![chart](docs/chart.png)\n",
            "src/docs/method.md": "Method. [back](../README.md)\n",
            "src/docs/chart.png": b"PNG",
            "src/sales/orders.tabledoc.yml": TABLE
            + "title: Orders\nprimary_key: [id]\nlisted: false\nlicenses: [own, CC0-1.0]\nsources: [site]\n"
            + "temporal_coverage: {start: 2020, end: '2024'}\nmetrics: [{name: n, agg: count, expr: id}]\n"
            + "columns:\n  - {name: id, description: The order, entity: {type: primary, name: order}}\n"
            + "  - {name: file, asset: true, annotations: {other: {wide: true}}}\n",
            "src/sales/orders.md": "Guide.\n",
        }
    ) / "src"
    report = Report()
    found = load(Options(root, with_source=False), Target(*catalog, unlisted=True), report)
    assert found is not None, report.render()
    files = tmp_path / "assets"
    files.mkdir()
    for file in found.files:
        (files / file.sha256).write_bytes(found.content(file))
    return catalog, files


def rows(catalog):
    with attached(*catalog) as con:
        return {table: sorted(map(repr, found)) for table, found in tables.read(con, ALIAS).items()}


def test_dump_writes_what_loads_to_the_same_tables(loaded, tmp_path):
    catalog, files = loaded
    out = tmp_path / "dumped"
    written = dump(Source(catalog[0], files.as_posix(), "shop"), out)
    assert written == [
        "README.md",
        "docs/chart.png",
        "method.md",
        "sales/orders.tabledoc.yml",
        "sales/orders/README.md",
        "tabledoc.yml",
    ]
    assert (out / "tabledoc.yml").read_text() == (
        "$schema: https://tabledoc.queria.io/schemas/dataset/v1.json\n"
        "name: shop\n"
        "title: Shop\n"
        "title_reading: ショップ\n"
        "description: |-\n  Two\n  lines\n"
        "topics:\n- trade\n"
        "issued: '2026-10-30'\n"
        "licenses:\n- CC-BY-4.0\n- id: own\n  commercial_use: false\n"
        "sources:\n- id: site\n  title: Site\n"
        "spatial_coverage:\n- JP\n"
        "contributors:\n- id: me\n  title: Me\n  roles:\n  - publisher\n"
        "image: docs/chart.png\n"
        "schemas:\n- name: sales\n  title: Sales\n"
        "documents:\n- method.md\n"
    )
    table = (out / "sales" / "orders.tabledoc.yml").read_text()
    assert "listed: false\nlicenses:\n- own\n- CC0-1.0\nsources:\n- site\n" in table
    assert "temporal_coverage:\n  start: '2020'\n  end: '2024'\n" in table
    assert (out / "method.md").read_text() == "Method. [back](README.md)\n"
    assert "sales/extra" not in written
    before = rows(catalog)
    report = Report()
    assert load(Options(out, with_source=False), Target(*catalog, unlisted=True), report) is not None, (
        report.render()
    )
    assert rows(catalog) == before


def test_dump_refuses_to_replace_files(loaded, tmp_path):
    catalog, files = loaded
    out = tmp_path / "dumped"
    out.mkdir()
    (out / "tabledoc.yml").write_text("mine\n")
    with pytest.raises(SpecError, match="--force"):
        dump(Source(catalog[0], files.as_posix(), "shop"), out)
    assert (out / "tabledoc.yml").read_text() == "mine\n"
    dump(Source(catalog[0], files.as_posix(), "shop"), out, force=True)
    assert (out / "tabledoc.yml").read_text().startswith("$schema")


def test_dump_checks_the_content(loaded, tmp_path):
    catalog, files = loaded
    victim = next(files.iterdir())
    victim.write_bytes(b"changed")
    with pytest.raises(SpecError, match="sha256"):
        dump(Source(catalog[0], files.as_posix(), "shop"), tmp_path / "dumped")


def test_dump_reads_the_repository_from_fdl_clones_note(loaded, tmp_path, monkeypatch, capsys):
    catalog, files = loaded
    repo = tmp_path / "repo"
    (repo / "assets").mkdir(parents=True)
    for file in files.iterdir():
        (repo / "assets" / file.name).write_bytes(file.read_bytes())
    (tmp_path / "lake" / "work.sqlite.fdl.json").write_text(json.dumps({"remote": str(repo) + "/"}))
    monkeypatch.setenv("FDL_WORKING", catalog[0])
    out = tmp_path / "dumped"
    assert main(["dump", "--out", str(out)]) == 0
    assert "name: repo\n" in (out / "tabledoc.yml").read_text()
    assert main(["dump", "--out", str(tmp_path / ".fdl" / "x")]) == 2
    assert ".fdl" in capsys.readouterr().err


def test_dump_writes_a_schema_other_than_tabledoc(write, lake, tmp_path):
    catalog = lake("CREATE SCHEMA lake.sales; CREATE TABLE lake.sales.orders AS SELECT 1 AS id")
    root = write({"src/tabledoc.yml": DATASET + "name: shop\ntitle: Shop\n", "src/sales/orders.tabledoc.yml": TABLE + "title: O\n"}) / "src"
    report = Report()
    assert load(Options(root, with_source=False), Target(*catalog, schema="docs"), report) is not None, report.render()
    out = tmp_path / "dumped"
    dump(Source(catalog[0], None, "shop", "docs"), out)
    assert "schema: docs\n" in (out / "tabledoc.yml").read_text()


def test_dump_refuses_a_path_outside_the_folder(loaded, tmp_path):
    catalog, files = loaded
    with attached(*catalog) as con:
        con.execute("UPDATE lake._tabledoc.files SET path = '../escaped.md' WHERE path = 'method.md'")
    with pytest.raises(SpecError, match="escaped"):
        dump(Source(catalog[0], files.as_posix(), "shop"), tmp_path / "dumped")
    assert not (tmp_path / "escaped.md").exists()


def test_dump_does_not_make_a_catalog(tmp_path):
    missing = tmp_path / "typo.sqlite"
    with pytest.raises(SpecError):
        dump(Source(str(missing)), tmp_path / "dumped")
    assert not missing.exists()


def test_text_in_more_than_one_language_comes_back_as_a_map(write, lake, tmp_path):
    catalog = lake("CREATE SCHEMA lake.sales; CREATE TABLE lake.sales.orders AS SELECT 1 AS id")
    root = write(
        {
            "src/tabledoc.yml": DATASET + "name: shop\nlanguage: ja\ntitle: {ja: 店, en: Shop}\ndescription: 店の注文\n",
            "src/sales/orders.tabledoc.yml": TABLE + "columns: [{name: id, title: {en: Order ID}}]\n",
        }
    ) / "src"
    report = Report()
    assert load(Options(root, with_source=False), Target(*catalog), report) is not None, report.render()
    out = tmp_path / "dumped"
    dump(Source(catalog[0], None, "shop"), out)
    dataset = (out / "tabledoc.yml").read_text()
    assert "title:\n  en: Shop\n  ja: 店\ndescription: 店の注文\n" in dataset
    assert "title:\n    en: Order ID\n" in (out / "sales" / "orders.tabledoc.yml").read_text()
    again = Report()
    assert load(Options(out, with_source=False), Target(*catalog), again) is not None, again.render()
