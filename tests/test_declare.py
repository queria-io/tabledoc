from __future__ import annotations

import json

import pytest

from tabledoc import Options, tables
from tabledoc.declare import commands, declare, wanted
from tabledoc.description import read
from tabledoc.report import Report, SpecError

DATASET = "$schema: https://tabledoc.queria.io/schemas/dataset/v1.json\nname: shop\n"
TABLE = "$schema: https://tabledoc.queria.io/schemas/table/v1.json\n"


def described(write):
    root = write(
        {
            "tabledoc.yml": DATASET,
            "sales/orders.tabledoc.yml": TABLE + "primary_key: [id]\ncolumns:\n  - {name: id}\n  - {name: file, asset: true}\n",
            "sales/extra.tabledoc.yml": TABLE + "description: Extra.\n",
        }
    )
    return read(Options(root, with_source=False), Report())


def test_declares_keys_and_assets_of_the_description_and_its_own_tables(write):
    want = wanted(described(write), "_tabledoc")
    assert want["primary_keys"]["sales.orders"] == ["id"]
    assert want["primary_keys"]["_tabledoc.columns"] == ["schema_name", "table_name", "column_name"]
    assert "sales.extra" not in want["primary_keys"]
    assert want["assets"] == {"sales.orders": ["file"], "_tabledoc.files": ["sha256"]}


def test_runs_only_what_differs(write):
    want = wanted(described(write), "_tabledoc")
    assert commands(want, want) == []
    have = {**want, "primary_keys": {**want["primary_keys"], "sales.orders": ["file"]}}
    assert commands(have, want) == [["primary-key", "sales.orders", "id"]]


def test_runs_fdl_declare_only_for_a_working_metadata(write, tmp_path):
    description = described(write)
    calls = []

    def run(args):
        calls.append(args)
        return json.dumps({}) if args[1] == "list" else ""

    catalog = tmp_path / "work.sqlite"
    assert declare(str(catalog), description, "_tabledoc", run) == []
    (tmp_path / "work.sqlite.fdl").mkdir()
    done = declare(str(catalog), description, "_tabledoc", run)
    assert calls[0] == ["declare", "list", str(catalog), "--json"]
    assert ["declare", "primary-key", str(catalog), "sales.orders", "id"] in calls
    assert ["declare", "assets", str(catalog), "_tabledoc.files", "sha256"] in calls
    assert len(calls) == len(done) + 1


def test_a_view_gets_no_key_and_a_table_not_listed_no_profile(write):
    want = wanted(described(write), "_tabledoc", unlisted={"sales.extra"}, views={"sales.orders"})
    assert "sales.orders" not in want["primary_keys"]
    assert "sales.orders" not in want["assets"]
    assert want["unprofiled"] == sorted([*(f"_tabledoc.{t}" for t in tables.TABLES), "sales.extra"])
    assert want["profiled"] == ["sales.orders"]
    have = {**want, "unprofiled": ["sales.orders"]}
    done = commands(have, want)
    assert ["profile", "sales.extra", "false"] in done
    assert ["profile", "sales.orders", "true"] in done
    assert commands(want, want) == []


def test_output_of_fdl_that_is_not_json_is_an_error(write, tmp_path):
    (tmp_path / "work.sqlite.fdl").mkdir()
    with pytest.raises(SpecError):
        declare(str(tmp_path / "work.sqlite"), described(write), "_tabledoc", lambda args: "not json")


def test_the_folder_fdl_keeps_beside_it_makes_a_working_metadata(tmp_path):
    from tabledoc.fdl_state import working

    catalog = tmp_path / "work.sqlite"
    assert working(str(catalog)) is None
    (tmp_path / "work.sqlite.fdl").mkdir()
    assert working(f"ducklake:{catalog}") == catalog