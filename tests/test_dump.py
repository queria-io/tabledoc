from __future__ import annotations

import json

import pytest

from tabledoc import Options
from tabledoc.cli import main
from tabledoc.dump import Source, dump
from tabledoc.load import ALIAS, Target, attached, load
from tabledoc.report import Report, SpecError

DATASET = "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\n"
TABLE = "$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json\n"


@pytest.fixture
def loaded(write, tmp_path):
    """A catalog loaded from a description, and the folder of its files by sha256."""
    path = tmp_path / "lake" / "work.sqlite"
    data = tmp_path / "lake" / "data"
    data.mkdir(parents=True)
    with attached(str(path), data.as_posix() + "/") as con:
        con.execute(f"CREATE SCHEMA {ALIAS}.sales")
        con.execute(f"CREATE TABLE {ALIAS}.sales.orders AS SELECT 1 AS id, 'a' AS file")
        con.execute(f"CREATE TABLE {ALIAS}.sales.extra AS SELECT 1 AS x")
    root = write(
        {
            "src/tabledoc.yml": DATASET
            + "name: shop\ntitle: Shop\ndescription: |-\n  Two\n  lines\nlicenses: [CC-BY-4.0]\nissued: 2026-10-30\n"
            + "schemas: [{name: sales, title: Sales}]\ndocs: [docs/method.md]\n"
            + "queria: {themes: [trade], title_kana: ショップ}\n",
            "src/README.md": "Overview. ![chart](docs/chart.png)\n",
            "src/docs/method.md": "Method. [back](../README.md)\n",
            "src/docs/chart.png": b"PNG",
            "src/sales/orders.yml": TABLE
            + "title: Orders\nprimary_key: [id]\nqueria: {published: false}\n"
            + "columns:\n  - {name: id, description: The order, entity: {type: primary, name: order}}\n"
            + "  - {name: file, asset: true, annotations: {other: {wide: true}}}\n",
            "src/sales/orders.md": "Guide.\n",
        }
    ) / "src"
    report = Report()
    found = load(Options(root, with_source=False), Target(str(path), data.as_posix() + "/", unlisted=True), report)
    assert found is not None, report.render()
    files = tmp_path / "assets"
    files.mkdir()
    for file in found.files:
        (files / file.sha256).write_bytes(found.content(file))
    return path, data.as_posix() + "/", files


def rows(path, data):
    with attached(str(path), data) as con:
        return {
            table: con.execute(f'SELECT * FROM {ALIAS}._fdl."{table}" ORDER BY ALL').fetchall()
            for table in ("dataset", "schemas", "tables", "columns", "files", "catalogs", "attributes")
        }


def test_dump_writes_what_loads_to_the_same_fdl(loaded, tmp_path):
    path, data, files = loaded
    out = tmp_path / "dumped"
    written = dump(Source(str(path), files.as_posix(), "shop"), out)
    assert written == [
        "README.md",
        "docs/chart.png",
        "method.md",
        "sales/orders.yml",
        "sales/orders/README.md",
        "tabledoc.yml",
    ]
    assert (out / "tabledoc.yml").read_text() == (
        "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\n"
        "name: shop\n"
        "title: Shop\n"
        "description: |-\n  Two\n  lines\n"
        "issued: '2026-10-30'\n"
        "licenses:\n- CC-BY-4.0\n"
        "schemas:\n- name: sales\n  title: Sales\n"
        "docs:\n- method.md\n"
        "queria:\n  themes:\n  - trade\n  title_kana: ショップ\n"
    )
    assert (out / "method.md").read_text() == "Method. [back](README.md)\n"
    assert "sales/extra" not in written
    before = rows(path, data)
    report = Report()
    assert load(Options(out, with_source=False), Target(str(path), data, unlisted=True), report) is not None, (
        report.render()
    )
    assert rows(path, data) == before


def test_dump_refuses_to_replace_files(loaded, tmp_path):
    path, _, files = loaded
    out = tmp_path / "dumped"
    out.mkdir()
    (out / "tabledoc.yml").write_text("mine\n")
    with pytest.raises(SpecError, match="--force"):
        dump(Source(str(path), files.as_posix(), "shop"), out)
    assert (out / "tabledoc.yml").read_text() == "mine\n"
    dump(Source(str(path), files.as_posix(), "shop"), out, force=True)
    assert (out / "tabledoc.yml").read_text().startswith("$schema")


def test_dump_checks_the_content(loaded, tmp_path):
    path, _, files = loaded
    victim = next(files.iterdir())
    victim.write_bytes(b"changed")
    with pytest.raises(SpecError, match="sha256"):
        dump(Source(str(path), files.as_posix(), "shop"), tmp_path / "dumped")


def test_dump_reads_the_repository_from_fdl_clones_note(loaded, tmp_path, monkeypatch, capsys):
    path, _, files = loaded
    repo = tmp_path / "repo"
    (repo / "assets").mkdir(parents=True)
    for file in files.iterdir():
        (repo / "assets" / file.name).write_bytes(file.read_bytes())
    (tmp_path / "lake" / "work.sqlite.fdl.json").write_text(json.dumps({"remote": str(repo) + "/"}))
    monkeypatch.setenv("FDL_WORKING", str(path))
    out = tmp_path / "dumped"
    assert main(["dump", "--out", str(out)]) == 0
    assert "name: repo\n" in (out / "tabledoc.yml").read_text()
    assert main(["dump", "--out", str(tmp_path / ".fdl" / "x")]) == 2
    assert ".fdl" in capsys.readouterr().err
