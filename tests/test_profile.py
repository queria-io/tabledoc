from __future__ import annotations

from pathlib import Path

import pytest

from tabledoc import tables
from tabledoc.cli import main
from tabledoc.load import ALIAS, attached
from tabledoc.profile import Target, profile
from tabledoc.report import SpecError


def held(catalog, table, *columns):
    """The rows of ``_tabledoc.<table>`` as tuples of ``columns``, sorted."""
    with attached(*catalog) as con:
        return con.execute(f"SELECT {', '.join(columns)} FROM {ALIAS}._tabledoc.{table} ORDER BY ALL").fetchall()


@pytest.fixture
def catalog(lake):
    return lake(
        "CREATE SCHEMA lake.sales;"
        "CREATE TABLE lake.sales.orders AS SELECT * FROM (VALUES "
        "(1, 'a', DATE '2025-01-01', true), (2, 'b', DATE '2025-03-01', NULL), (3, 'a', NULL, false)) t(id, city, day, paid);"
        "CREATE TABLE lake.sales.many AS SELECT range AS n, range::VARCHAR AS s FROM range(2500);"
        "CREATE VIEW lake.sales.cities AS SELECT DISTINCT city FROM lake.sales.orders"
    )


def test_counts_every_table_and_view(catalog):
    profile(Target(*catalog))
    assert held(catalog, "table_profiles", "schema_name", "table_name", "rows") == [
        ("sales", "cities", 2),
        ("sales", "many", 2500),
        ("sales", "orders", 3),
    ]
    orders = [r for r in held(catalog, "column_profiles", "table_name", "column_name", "null_count", "distinct_count", "min", "max") if r[0] == "orders"]
    assert orders == [
        ("orders", "city", 0, 2, None, None),
        ("orders", "day", 1, 2, "2025-01-01", "2025-03-01"),
        ("orders", "id", 0, 3, "1", "3"),
        ("orders", "paid", 1, None, None, None),
    ]
    values = held(catalog, "column_values", "table_name", "column_name", "value", "count")
    assert ("orders", "city", "a", 2) in values
    assert not [v for v in values if v[1] == "paid"]


def test_lists_the_most_common_above_the_limit(catalog):
    profile(Target(*catalog))
    many = [r for r in held(catalog, "column_profiles", "table_name", "column_name", "distinct_count") if r[0] == "many"]
    assert many == [("many", "n", 2500), ("many", "s", 2500)]
    listed = [r for r in held(catalog, "column_values", "table_name", "column_name") if r[0] == "many"]
    assert len(listed) == 20


def test_counts_again_without_the_rows_of_before(catalog):
    profile(Target(*catalog))
    with attached(*catalog) as con:
        con.execute("DROP VIEW lake.sales.cities; DELETE FROM lake.sales.orders WHERE id = 3")
    profile(Target(*catalog))
    assert held(catalog, "table_profiles", "table_name", "rows") == [("many", 2500), ("orders", 2)]
    assert not [r for r in held(catalog, "column_values", "table_name") if r[0] == "cities"]


def test_skips_hidden_tables(catalog):
    with attached(*catalog) as con:
        tables.write(con, ALIAS, {"tables": [{"schema_name": "sales", "table_name": "many", "hidden": True}]})
    profile(Target(*catalog))
    assert held(catalog, "table_profiles", "table_name") == [("cities",), ("orders",)]


def test_refuses_fdl_working_metadata(catalog):
    Path(catalog[0] + ".fdl").mkdir()
    with pytest.raises(SpecError, match="fdl writes the profiles"):
        profile(Target(*catalog))


def test_cli(catalog, capsys):
    assert main(["profile", "--ducklake", catalog[0], "--data-path", catalog[1]]) == 0
    assert "profiled 3 tables and views" in capsys.readouterr().err
