"""tabledoc profile: count the data of a DuckLake catalog into the profile tables.

`table_profiles`, `column_profiles` and `column_values` of the description's schema
hold what an FDL profile holds, under the same names and by the same rules
(`ALL_VALUES`, `TOP_VALUES`). Each run counts every table and view again by SQL
and makes the tables hold that and nothing else. A catalog `fdl clone` made is
refused: fdl writes a profile for each version itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import fdl_state, tables
from .load import ALIAS, attached, data_path
from .report import SpecError

#: A column with at most this many distinct values lists them all, as FDL's profile does.
ALL_VALUES = 2000
#: Otherwise the most common.
TOP_VALUES = 10
#: Above this many rows, distinct values are estimated rather than counted.
EXACT_DISTINCT_ROWS = 1_000_000
#: Columns counted by one query: each `count(DISTINCT)` holds a hash table at once.
COLUMNS_PER_QUERY = 100

_NUMERIC = re.compile(r"^(U?(TINY|SMALL|BIG|HUGE)?INT(EGER)?|FLOAT|DOUBLE|REAL|DECIMAL|NUMERIC|U?INT\d+|FLOAT\d+)\b")
_TEMPORAL = re.compile(r"^(DATE|TIME|TIMESTAMP|INTERVAL)\b")
_TEXT = re.compile(r"^(VARCHAR|UUID)\b")


@dataclass(frozen=True)
class Target:
    #: The DuckLake catalog: a .sqlite or .duckdb file, or a ducklake: path.
    catalog: str
    #: Where the catalog's data files are, when not where it says.
    data_path: str | None = None
    #: The description's schema; default `_tabledoc`.
    schema: str | None = None


def kind(data_type: str) -> str:
    """numeric, temporal, text or other: which counts a column gets."""
    upper = data_type.upper()
    if _NUMERIC.match(upper):
        return "numeric"
    if _TEMPORAL.match(upper):
        return "temporal"
    if _TEXT.match(upper):
        return "text"
    return "other"


def _aggregates(name: str, data_type: str, rows: int) -> list[str]:
    """count, distinct count, min and max of one column, as one query's expressions."""
    c = tables.quote(name)
    family = kind(data_type)
    distinct = f"count(DISTINCT {c})" if rows <= EXACT_DISTINCT_ROWS else f"approx_count_distinct({c})"
    bounds = [f"min({c})::VARCHAR", f"max({c})::VARCHAR"] if family in ("numeric", "temporal") else ["NULL", "NULL"]
    return [f"count({c})", distinct if family != "other" else "NULL", *bounds]


def _values(con: Any, relation: str, name: str, distinct: int) -> tuple[int, list[tuple[str, int]]]:
    """(distinct count, values with their counts): every value when there are at most `ALL_VALUES`,
    and then the count is exact; else the `TOP_VALUES` most common, and at least `ALL_VALUES` + 1."""
    found = con.execute(
        f"SELECT {tables.quote(name)}::VARCHAR, count(*) FROM {relation} WHERE {tables.quote(name)} IS NOT NULL "
        f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {ALL_VALUES + 1}"
    ).fetchall()
    if len(found) <= ALL_VALUES:
        return len(found), found
    return max(distinct, ALL_VALUES + 1), found[:TOP_VALUES]


def _columns(con: Any, relation: str, held: dict[str, str]) -> list[tuple[str, str]]:
    """(name, type) of each column: as the catalog holds them, or as a view's query returns them."""
    if held:
        return list(held.items())
    return [(row[0], row[1]) for row in con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()]


def count(con: Any, schema: str, table: str, held: dict[str, str]) -> tables.Rows:
    """The profile rows of one table or view."""
    relation = f"{ALIAS}.{tables.quote(schema)}.{tables.quote(table)}"
    columns = _columns(con, relation, held)
    rows = int(con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
    counted: list[Any] = []
    for start in range(0, len(columns), COLUMNS_PER_QUERY):
        exprs = [e for n, t in columns[start : start + COLUMNS_PER_QUERY] for e in _aggregates(n, t, rows)]
        counted += con.execute(f"SELECT {', '.join(exprs)} FROM {relation}").fetchone() if exprs else []
    at = {"schema_name": schema, "table_name": table}
    profiles, values = [], []
    for i, (name, data_type) in enumerate(columns):
        present, distinct, low, high = counted[i * 4 : i * 4 + 4]
        listed: list[tuple[str, int]] = []
        if distinct is not None:
            distinct, listed = _values(con, relation, name, int(distinct))
        profiles.append(
            {**at, "column_name": name, "null_count": rows - int(present), "distinct_count": distinct, "min": low, "max": high}
        )
        values += [{**at, "column_name": name, "value": v, "count": int(n)} for v, n in listed]
    return {"table_profiles": [{**at, "rows": rows}], "column_profiles": profiles, "column_values": values}


def _hidden(con: Any, schema: str) -> set[tables.Key]:
    """The tables the description hides: they get no profile, as with FDL."""
    return {
        tables.fold(t["schema_name"], t["table_name"])
        for t in tables.read(con, ALIAS, schema).get("tables") or []
        if tables.hidden(t)
    }


def profile(target: Target) -> tables.Rows:
    """Count every table and view of the catalog (but the description's own and hidden ones)
    and make the profile tables of the description's schema hold the counts and nothing else."""
    if fdl_state.working(target.catalog) is not None:
        raise SpecError(f"{target.catalog} is fdl's working metadata: fdl writes the profiles of each version")
    import duckdb

    schema = target.schema or tables.SCHEMA
    try:
        with attached(target.catalog, data_path(target.catalog, target.data_path)) as con:
            schema = tables.spelled_schema(con, ALIAS, schema)
            in_catalog, views, columns = tables.relations(con, ALIAS, schema)
            hidden = _hidden(con, schema)
            found: tables.Rows = {name: [] for name in tables.PROFILES}
            for key in sorted(in_catalog | views):
                if tables.fold(*key) in hidden:
                    continue
                for name, rows in count(con, *key, columns[key]).items():
                    found[name] += rows
            tables.write_profiles(con, ALIAS, found, schema)
    except duckdb.Error as exc:
        raise SpecError(f"cannot profile {target.catalog}: {exc}") from exc
    return found
