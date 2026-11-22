"""A description as the rows of the `_fdl` schema, which FDL defines (https://fdl.queria.io/spec/fdl-schema).

    _fdl.dataset      one row: the dataset's title, description, licenses...
    _fdl.schemas      one row per schema described          key: schema
    _fdl.tables       one row per table or view             key: schema, name
    _fdl.columns      one row per column described          key: schema, table, name
    _fdl.files        the documents and what they link to   key: path
    _fdl.catalogs     the other datasets the views read     key: name
    _fdl.attributes   keys for one reader                   key: schema, table, column, key

The tables are dropped and written again each time, in one transaction.
"""

from __future__ import annotations

import datetime
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from .description import Description
from .shape import BUILT_KEYS, QUERIA

SCHEMA = "_fdl"
#: The schema tabledoc 0.3 wrote; load drops it.
OLD_SCHEMA = "_meta"

_LICENSE = (
    "STRUCT(id VARCHAR, spdx VARCHAR, url VARCHAR, title VARCHAR, "
    "commercial_use BOOLEAN, share_alike BOOLEAN, attribution_required BOOLEAN)[]"
)
_SOURCE = "STRUCT(title VARCHAR, path VARCHAR)[]"
_CONTRIBUTOR = "STRUCT(title VARCHAR, path VARCHAR, roles VARCHAR[])[]"
_TEMPORAL = 'STRUCT(start VARCHAR, "end" VARCHAR)'

#: Each table: its columns and types, in order, and its primary key.
TABLES: dict[str, tuple[dict[str, str], list[str]]] = {
    "dataset": (
        {
            "title": "VARCHAR",
            "description": "VARCHAR",
            "language": "VARCHAR",
            "topics": "VARCHAR[]",
            "homepage": "VARCHAR",
            "issued": "DATE",
            "update_frequency": "VARCHAR",
            "licenses": _LICENSE,
            "sources": _SOURCE,
            "contributors": _CONTRIBUTOR,
            "temporal_coverage": _TEMPORAL,
            "spatial_coverage": "VARCHAR[]",
        },
        [],
    ),
    "schemas": ({"schema": "VARCHAR", "title": "VARCHAR", "description": "VARCHAR"}, ["schema"]),
    "tables": (
        {
            "schema": "VARCHAR",
            "name": "VARCHAR",
            "title": "VARCHAR",
            "description": "VARCHAR",
            "topics": "VARCHAR[]",
            "licenses": _LICENSE,
            "sources": _SOURCE,
            "temporal_coverage": _TEMPORAL,
            "spatial_coverage": "VARCHAR[]",
            "primary_key": "VARCHAR[]",
            "profile": "BOOLEAN",
            "sql": "VARCHAR",
            "depends_on": "VARCHAR[]",
            "materialized": "VARCHAR",
            "source_path": "VARCHAR",
        },
        ["schema", "name"],
    ),
    "columns": (
        {
            "schema": "VARCHAR",
            "table": "VARCHAR",
            "name": "VARCHAR",
            "title": "VARCHAR",
            "description": "VARCHAR",
            "entity": "VARCHAR",
            "asset": "BOOLEAN",
        },
        ["schema", "table", "name"],
    ),
    "files": (
        {"path": "VARCHAR", "sha256": "VARCHAR", "bytes": "BIGINT", "media_type": "VARCHAR"},
        ["path"],
    ),
    "catalogs": ({"name": "VARCHAR", "url": "VARCHAR"}, ["name"]),
    "attributes": (
        {"schema": "VARCHAR", "table": "VARCHAR", "column": "VARCHAR", "key": "VARCHAR", "value": "JSON"},
        ["schema", "table", "column", "key"],
    ),
}

Rows = dict[str, list[dict[str, Any]]]
Key = tuple[str, str]


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _pick(record: dict[str, Any], columns: list[str] | tuple[str, ...]) -> dict[str, Any]:
    return {c: record[c] for c in columns if _present(record.get(c))}


def _licenses(value: Any) -> list[dict[str, Any]] | None:
    """Licenses as written: an id alone, or the id with its terms."""
    if not isinstance(value, list):
        return None
    return [{"id": v} if isinstance(v, str) else v for v in value if isinstance(v, (str, dict))] or None


def _record(record: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    licenses = _licenses(record.get("licenses"))
    return {**_pick(record, columns), **({"licenses": licenses} if licenses else {})}


def _entity(column: dict[str, Any]) -> str | None:
    entity = column.get("entity")
    return entity.get("name") if isinstance(entity, dict) else None


def attribute_key(reader: str, key: str) -> str:
    """The key of `_fdl.attributes` for ``key`` under ``reader``: `queria` and `title_kana` give `queria-title-kana`."""
    return f"{reader}-{key.replace('_', '-')}"


def split_key(key: str) -> tuple[str, str]:
    """(reader, key as written in YAML) of a key of `_fdl.attributes`."""
    reader, _, rest = key.partition("-")
    return reader, rest.replace("-", "_")


def _attributes(record: dict[str, Any], schema: str = "", table: str = "", column: str = "") -> list[dict[str, Any]]:
    """One row per key of each reader under `annotations` (`queria:` among them)."""
    readers = record.get("annotations") or {}
    return [
        {"schema": schema, "table": table, "column": column, "key": attribute_key(reader, key), "value": value}
        for reader, keys in readers.items()
        if isinstance(keys, dict)
        for key, value in keys.items()
    ]


def published(table: dict[str, Any]) -> bool:
    """Whether Queria lists a described table: unless `published` under `queria:` is false."""
    own = (table.get("annotations") or {}).get(QUERIA) or {}
    return not (isinstance(own, dict) and own.get("published") is False)


def fold(*names: str) -> tuple[str, ...]:
    """``names`` as DuckDB compares identifiers: without regard to case."""
    return tuple(n.lower() for n in names)


def rows(
    description: Description,
    carried: Rows | None = None,
    unlisted: set[Key] | None = None,
    views: set[Key] | None = None,
) -> Rows:
    """The rows of each `_fdl` table for ``description``.

    ``carried`` is the `_fdl` the catalog held: a table without `sql` (nothing
    was built) keeps `materialized`, `sql`, `depends_on` and `source_path` from
    it. ``unlisted`` are the catalog's tables with no description: Queria does
    not list them and they get no profile. ``views`` are the catalog's views,
    whose SQL the metadata already holds.
    """
    columns = {name: list(spec[0]) for name, spec in TABLES.items()}
    built = not carried or any("sql" in t for t in description.tables)
    kept = {} if built else {fold(t["schema"], t["name"]): t for t in carried.get("tables") or []}
    described = {fold(t["schema"], t["name"]) for t in description.tables}
    viewed = {fold(*v) for v in views or set()}
    no_profile = {"profile": False}

    def table(t: dict[str, Any]) -> dict[str, Any]:
        key = fold(t["schema"], t["name"])
        record = {**_pick(kept.get(key, {}), BUILT_KEYS), **_record(t, columns["tables"][2:])}
        if key in viewed:
            record.pop("sql", None)
        return {"schema": t["schema"], "name": t["name"], **record, **({} if published(t) else no_profile)}

    unlisted_keys = [(s, n) for s, n in sorted(unlisted or set()) if fold(s, n) not in described]
    return {
        "dataset": [d] if (d := _record(description.dataset, columns["dataset"])) else [],
        "schemas": [
            {"schema": s["name"], **_pick(s, ["title", "description"])}
            for s in description.schemas
            if s.get("title") or s.get("description")
        ],
        "tables": [table(t) for t in description.tables]
        + [{"schema": s, "name": n, **no_profile} for s, n in unlisted_keys],
        "columns": [
            {
                "schema": t["schema"],
                "table": t["name"],
                "name": c["name"],
                **_pick({**c, "entity": _entity(c)}, ["title", "description", "entity"]),
                **({"asset": True} if c.get("asset") is True else {}),
            }
            for t in description.tables
            for c in t.get("columns") or []
            if c.get("name") and (c.get("title") or c.get("description") or _entity(c) or c.get("asset") is True)
        ],
        "files": [f.entry() for f in description.files],
        "catalogs": [{"name": k, "url": v} for k, v in sorted((description.catalogs or {}).items())],
        "attributes": _attributes(description.dataset)
        + [a for t in description.tables for a in _attributes(t, t["schema"], t["name"])]
        + [
            a
            for t in description.tables
            for c in t.get("columns") or []
            if c.get("name")
            for a in _attributes(c, t["schema"], t["name"], c["name"])
        ]
        + [
            {"schema": s, "table": n, "column": "", "key": attribute_key(QUERIA, "published"), "value": False}
            for s, n in unlisted_keys
        ],
    }


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fits(value: Any, kind: str) -> bool:
    """Whether DuckDB can read ``value`` as a column of type ``kind`` (its outer shape)."""
    if value is None or kind == "JSON":
        return True
    if kind == "DATE":
        if not (isinstance(value, str) and _DATE.match(value)):
            return False
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            return False
        return True
    if kind.endswith("[]"):
        return isinstance(value, list) and (kind != "VARCHAR[]" or all(isinstance(v, str) for v in value))
    if kind.startswith("STRUCT"):
        return isinstance(value, dict)
    if kind == "BOOLEAN":
        return isinstance(value, bool)
    if kind in ("INTEGER", "BIGINT"):
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def unfit(found: Rows) -> list[tuple[str, str, str]]:
    """(where, column, type) of each value in ``found`` its `_fdl` column cannot hold.

    `issued` is any text in the JSON Schema; DuckDB refuses it here unless it is a date.
    """
    wrong = []
    for table, records in found.items():
        columns = TABLES[table][0]
        for record in records:
            key = ".".join(str(record[k]) for k in TABLES[table][1] if record.get(k))
            where = f"{SCHEMA}.{table}" + (f" {key}" if key else "")
            for column, value in record.items():
                kind = columns.get(column)
                if kind is not None and not _fits(value, kind):
                    wrong.append((where, column, kind))
    return wrong


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: str | None) -> str:
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


def write(con: Any, catalog: str, found: Rows) -> None:
    """Write ``found`` as the `_fdl` tables of ``catalog`` (attached on ``con``), and drop `_meta`.

    In one transaction: a row DuckDB refuses (a date out of range, say) leaves
    the catalog as it was.
    """
    con.execute("BEGIN")
    try:
        _drop_old(con, catalog)
        _write(con, catalog, found)
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


def _drop_old(con: Any, catalog: str) -> None:
    """The `_meta` schema tabledoc 0.3 wrote, which `_fdl` replaces."""
    old = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = ? AND schema_name = ?", [catalog, OLD_SCHEMA]
    ).fetchall()
    for (name,) in old:
        con.execute(f"DROP TABLE {catalog}.{OLD_SCHEMA}.{quote(name)}")
    if con.execute(
        "SELECT 1 FROM duckdb_schemas() WHERE database_name = ? AND schema_name = ?", [catalog, OLD_SCHEMA]
    ).fetchall():
        con.execute(f"DROP SCHEMA {catalog}.{OLD_SCHEMA}")


def _write(con: Any, catalog: str, found: Rows) -> None:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{SCHEMA}")
    with tempfile.TemporaryDirectory(prefix="tabledoc-fdl-") as tmp:
        for table, (columns, _) in TABLES.items():
            target = f"{catalog}.{SCHEMA}.{quote(table)}"
            con.execute(f"DROP TABLE IF EXISTS {target}")
            spec = ", ".join(f"{quote(c)} {t}" for c, t in columns.items())
            con.execute(f"CREATE TABLE {target} ({spec})")
            records = found.get(table) or []
            if not records:
                continue
            path = Path(tmp) / f"{table}.json"
            path.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records), encoding="utf-8"
            )
            typed = ", ".join(f"'{c}': {_literal(t)}" for c, t in columns.items())
            names = ", ".join(quote(c) for c in columns)
            con.execute(
                f"INSERT INTO {target} ({names}) SELECT {names} FROM read_json(?, "
                f"format = 'newline_delimited', columns = {{{typed}}})",
                [path.as_posix()],
            )


def read(con: Any, catalog: str, schema: str = SCHEMA) -> Rows | None:
    """The tables of ``schema`` (`_fdl`) ``catalog`` holds, or None when it has none.

    Values of a JSON column come back parsed.
    """
    found = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = ? AND schema_name = ?", [catalog, schema]
    ).fetchall()
    if not found:
        return None
    result: Rows = {}
    for (table,) in found:
        cursor = con.execute(f"SELECT * FROM {catalog}.{quote(schema)}.{quote(table)}")
        names = [d[0] for d in cursor.description]
        kinds = TABLES.get(table, ({}, []))[0] if schema == SCHEMA else {}
        result[table] = [
            {n: json.loads(v) if kinds.get(n) == "JSON" and isinstance(v, str) else v for n, v in zip(names, row)}
            for row in cursor.fetchall()
        ]
    return result


def relations(con: Any, catalog: str) -> tuple[set[Key], set[Key]]:
    """(tables, views) of ``catalog``, but those of `_fdl` and `_meta`."""
    found = con.execute(
        """
        SELECT schema_name, table_name, false FROM duckdb_tables() WHERE database_name = $1
        UNION ALL
        SELECT schema_name, view_name, true FROM duckdb_views() WHERE database_name = $1
        """,
        [catalog],
    ).fetchall()
    kept = [(s, n, v) for s, n, v in found if s not in (SCHEMA, OLD_SCHEMA)]
    return {(s, n) for s, n, v in kept if not v}, {(s, n) for s, n, v in kept if v}
