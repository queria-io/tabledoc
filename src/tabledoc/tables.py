"""A description as the rows of the tables of one schema (`_tabledoc` by default).

The tables are in third normal form: no lists, structs or JSON in a cell. Each
row is about one thing, named by `schema_name`, `table_name` and `column_name`;
a part that does not apply is `''`, so the dataset's rows have all three `''`.

    dataset             key, value: the dataset's one-valued keys
    schemas             each schema
    tables              each table and view: hidden, temporal coverage, sql, source_path
    columns             each column described or in the primary key: key_position, entity, dimension, granularity
    metrics             each metric of a table
    descriptions        title, title_reading and description, one row per language
    topics, synonyms    one row per word and language
    licenses, sources   by id; table_licenses and table_sources say which apply where
    contributors        by id, with contributor_roles
    table_areas         spatial coverage
    table_dependencies  the tables each table's SQL reads
    files               the documents and what they link to

`table_profiles`, `column_profiles` and `column_values` are part of the format too
(`PROFILES`), but `tabledoc load` does not write them. They are ordinary tables of
the catalog, versioned with the data. FDL does not know what they mean;
`files.sha256` is declared to it as an asset column.
"""

from __future__ import annotations

import datetime
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from . import languages, shape
from .description import Description
from .shape import BUILT_KEYS

SCHEMA = "_tabledoc"

_V = "VARCHAR"
_ON = {"schema_name": _V, "table_name": _V}
_WHERE = {**_ON, "column_name": _V}
_AT = tuple(_WHERE)

#: Each table: its columns and types, in order, and its primary key.
TABLES: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    "dataset": ({"key": _V, "value": _V}, ("key",)),
    "schemas": ({"schema_name": _V}, ("schema_name",)),
    "tables": (
        {**_ON, "hidden": "BOOLEAN", "temporal_start": _V, "temporal_end": _V, "sql": _V, "source_path": _V},
        tuple(_ON),
    ),
    "columns": ({**_WHERE, "key_position": "INTEGER", "entity": _V, "dimension": _V, "granularity": _V}, _AT),
    "metrics": ({**_ON, "metric_name": _V, "agg": _V, "expr": _V, "description": _V}, (*_ON, "metric_name")),
    "descriptions": ({**_WHERE, "language": _V, "title": _V, "title_reading": _V, "description": _V}, (*_AT, "language")),
    "topics": ({**_WHERE, "language": _V, "topic": _V}, (*_AT, "language", "topic")),
    "synonyms": ({**_WHERE, "language": _V, "synonym": _V}, (*_AT, "language", "synonym")),
    "licenses": (
        {
            "id": _V,
            "url": _V,
            "title": _V,
            "commercial_use": "BOOLEAN",
            "share_alike": "BOOLEAN",
            "attribution_required": "BOOLEAN",
        },
        ("id",),
    ),
    "table_licenses": ({**_ON, "license_id": _V, "position": "INTEGER"}, (*_ON, "license_id")),
    "sources": ({"id": _V, "title": _V, "url": _V}, ("id",)),
    "table_sources": ({**_ON, "source_id": _V, "position": "INTEGER"}, (*_ON, "source_id")),
    "contributors": ({"id": _V, "title": _V, "url": _V, "position": "INTEGER"}, ("id",)),
    "contributor_roles": ({"contributor_id": _V, "role": _V}, ("contributor_id", "role")),
    "table_areas": ({**_ON, "area": _V, "position": "INTEGER"}, (*_ON, "area")),
    "table_dependencies": ({**_ON, "depends_on": _V}, (*_ON, "depends_on")),
    "files": ({"path": _V, "sha256": _V, "bytes": "BIGINT", "media_type": _V}, ("path",)),
}

#: The optional profile tables: computed from the data, never merged, and not written by load.
#: They hold what an FDL profile holds, under the same names.
PROFILES: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    "table_profiles": ({**_ON, "rows": "BIGINT"}, tuple(_ON)),
    "column_profiles": (
        {**_WHERE, "null_count": "BIGINT", "distinct_count": "BIGINT", "min": _V, "max": _V},
        _AT,
    ),
    "column_values": ({**_WHERE, "value": _V, "count": "BIGINT"}, (*_AT, "value")),
}

#: The keys of the `dataset` table.
DATASET_KEYS = (
    "name",
    "language",
    "homepage",
    "repository",
    "issued",
    "update_frequency",
    "image",
    "temporal_start",
    "temporal_end",
)
#: Asset columns of the description's own tables, declared to FDL.
ASSETS = {"files": ("sha256",)}
#: Columns of `descriptions` that hold text, one language a row.
TEXTS = ("title", "title_reading", "description")
#: Tables an earlier tabledoc wrote that are not the format's now: a load drops them.
_EARLIER = frozenset({"texts"})
#: Tables every load wrote, an earlier tabledoc's too: a schema holding them all is a description's.
_EVERY_LOAD = frozenset({"dataset", "schemas", "tables", "columns", "files"})

Rows = dict[str, list[dict[str, Any]]]
Key = tuple[str, str]


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _text(value: Any) -> str | None:
    """A value of a text column: numbers (a year in temporal coverage, say) as text."""
    return None if value is None or value == "" else str(value)


def _entry(entry: dict[str, Any], keys: tuple[str, ...], language: str) -> dict[str, Any]:
    """``keys`` of a license, source or contributor, each text in ``language`` alone."""
    return {k: languages.one(entry[k], language) for k in keys if _present(entry.get(k))}


def several(description: Description) -> list[str]:
    """Where text written in more than one language goes into a table that holds one value:
    only the one in `language` is written. As ``<where>: <key>``."""
    found = []

    def look(where: str, record: dict[str, Any]) -> None:
        if languages.several(record.get("homepage")):
            found.append(f"{where}: homepage")
        for key in languages.LISTS:
            for e in record.get(key) or []:
                if isinstance(e, dict):
                    found.extend(f"{where}: {key}.{k}" for k, v in e.items() if languages.several(v))
        for m in record.get("metrics") or []:
            if languages.several(m.get("description")):
                found.append(f"{where}: metrics.{m.get('name')}.description")

    look("dataset", description.dataset)
    for t in description.tables:
        look(f"{t['schema']}.{t['name']}", t)
    return found


def fold(*names: str) -> tuple[str, ...]:
    """``names`` as DuckDB compares identifiers: without regard to case."""
    return tuple(n.lower() for n in names)


def _kept(carried: Rows) -> dict[tuple[str, ...], dict[str, Any]]:
    """What a build wrote of each table in ``carried``: `sql`, `source_path` and `depends_on`."""
    kept: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in carried.get("tables") or []:
        if row.get("schema_name") is None:
            continue  # an earlier tabledoc's row
        kept[fold(row["schema_name"], row["table_name"])] = {
            k: row[k] for k in ("sql", "source_path") if _present(row.get(k))
        }
    for row in carried.get("table_dependencies") or []:
        key = fold(row["schema_name"], row["table_name"])
        if key in kept:
            kept[key].setdefault("depends_on", []).append(row["depends_on"])
    return kept


def _words(where: tuple[str, str, str], value: Any, column: str) -> list[dict[str, Any]]:
    """Rows of `topics` or `synonyms`: one per word and language of ``value`` ({tag: [words]})."""
    schema, table, col = where
    return [
        {"schema_name": schema, "table_name": table, "column_name": col, "language": tag, column: word}
        for tag, words in sorted((value or {}).items())
        for word in dict.fromkeys(words or [])
    ]


def _about(record: dict[str, Any], where: tuple[str, str, str]) -> Rows:
    """The rows of `descriptions`, `topics` and `synonyms` for ``record`` at ``where``."""
    values = {k: record[k] for k in TEXTS if isinstance(record.get(k), dict)}
    tags = sorted({tag for value in values.values() for tag in value})
    schema, table, column = where
    return {
        "descriptions": [
            {
                "schema_name": schema,
                "table_name": table,
                "column_name": column,
                "language": tag,
                **{k: value[tag] for k, value in values.items() if tag in value},
            }
            for tag in tags
        ],
        "topics": _words(where, record.get("topics"), "topic"),
        "synonyms": _words(where, record.get("synonyms"), "synonym"),
    }


def _on(record: dict[str, Any], on: tuple[str, str], language: str) -> Rows:
    """The rows of `table_licenses`, `table_sources` and `table_areas` for ``record`` (the dataset, or a table)."""
    schema, table = on
    return {
        "table_licenses": [
            {"schema_name": schema, "table_name": table, "license_id": e["id"], "position": i}
            for i, e in enumerate(record.get("licenses") or [])
        ],
        "table_sources": [
            {"schema_name": schema, "table_name": table, "source_id": e["id"], "position": i}
            for i, e in enumerate(record.get("sources") or [])
        ],
        "table_areas": [
            {"schema_name": schema, "table_name": table, "area": a, "position": i}
            for i, a in enumerate(dict.fromkeys(record.get("spatial_coverage") or []))
        ],
    }


def _column(t: dict[str, Any], c: dict[str, Any]) -> dict[str, Any] | None:
    """The `columns` row of ``c``, when it says anything or is part of the primary key."""
    key = [str(k).lower() for k in t.get("primary_key") or []]
    name = c.get("name")
    position = key.index(str(name).lower()) if name and str(name).lower() in key else None
    picked = {k: c.get(k) for k in ("entity", "dimension", "granularity")}
    said = {k for k in (*TEXTS, "topics", "synonyms") if _present(c.get(k))} | {k for k, v in picked.items() if v}
    if not name or (not said and position is None):
        return None
    return {
        "schema_name": t["schema"],
        "table_name": t["name"],
        "column_name": name,
        **({"key_position": position} if position is not None else {}),
        **{k: v for k, v in picked.items() if v},
    }


def _merge(into: Rows, more: Rows) -> None:
    for table, found in more.items():
        into.setdefault(table, []).extend(found)


def rows(
    description: Description,
    carried: Rows | None = None,
    undescribed: set[Key] | None = None,
    views: set[Key] | None = None,
) -> Rows:
    """The rows of each table for ``description``.

    ``carried`` is what the catalog held: without a dbt build (no `sql` in the
    description), each table keeps its `sql`, `source_path` and dependencies from
    it. ``undescribed`` are the catalog's tables and views: those with no
    description, and those dbt built that say nothing but their SQL, are written
    with `hidden` true. ``views`` are the catalog's views, whose SQL the metadata
    already holds.
    """
    built = not carried or any("sql" in t for t in description.tables)
    kept = {} if built else _kept(carried or {})
    described = {fold(t["schema"], t["name"]) for t in description.tables}
    viewed = {fold(*v) for v in views or set()}

    # `repository` from tabledoc.yml, else Git's origin; `source_path` from its root.
    where = description.source or {}
    folder = where.get("path") or ""
    dataset = description.dataset
    language = str(dataset.get("language") or languages.UNDETERMINED)
    if not dataset.get("repository") and where.get("repository"):
        dataset = {**dataset, "repository": where["repository"]}

    found: Rows = {name: [] for name in TABLES}

    def table(t: dict[str, Any]) -> None:
        key = fold(t["schema"], t["name"])
        if t.get("source_path") and folder:
            t = {**t, "source_path": f"{folder}/{t['source_path']}"}
        t = {**kept.get(key, {}), **t}
        hidden = t.get("hidden")
        if hidden is None:
            hidden = undescribed is not None and not _said(t)
        coverage = t.get("temporal_coverage") or {}
        record = {
            "hidden": hidden,
            "temporal_start": _text(coverage.get("start")),
            "temporal_end": _text(coverage.get("end")),
            "sql": None if key in viewed else t.get("sql"),
            "source_path": t.get("source_path"),
        }
        on = (t["schema"], t["name"])
        found["tables"].append({"schema_name": on[0], "table_name": on[1], **{k: v for k, v in record.items() if v is not None}})
        if key not in viewed:
            # The metadata holds a view's SQL, and so what it reads.
            found["table_dependencies"] += [
                {"schema_name": on[0], "table_name": on[1], "depends_on": d} for d in dict.fromkeys(t.get("depends_on") or [])
            ]
        _merge(found, _about(t, (*on, "")))
        _merge(found, _on(t, on, language))
        written = t.get("columns") or []
        named = {str(c.get("name")).lower() for c in written}
        keyed = [{"name": k} for k in t.get("primary_key") or [] if str(k).lower() not in named]
        for c in [*written, *keyed]:
            row = _column(t, c)
            if row is not None:
                found["columns"].append(row)
                _merge(found, _about(c, (*on, c["name"])))
        found["metrics"] += [
            {
                "schema_name": on[0],
                "table_name": on[1],
                "metric_name": m["name"],
                **_entry({**m, "description": m.get("description")}, ("agg", "expr", "description"), language),
            }
            for m in t.get("metrics") or []
        ]

    for t in description.tables:
        table(t)
    for s, n in sorted(undescribed or set()):
        if fold(s, n) not in described:
            table({"schema": s, "name": n})

    coverage = dataset.get("temporal_coverage") or {}
    values = {
        **{k: dataset.get(k) for k in DATASET_KEYS},
        "homepage": languages.one(dataset.get("homepage"), language),
        "temporal_start": _text(coverage.get("start")),
        "temporal_end": _text(coverage.get("end")),
    }
    found["dataset"] = [{"key": k, "value": str(v)} for k, v in values.items() if _present(v)]
    _merge(found, _about(dataset, ("", "", "")))
    _merge(found, _on(dataset, ("", ""), language))
    for s in description.schemas:
        _merge(found, _about(s, (s["name"], "", "")))
    names = {s["name"] for s in description.schemas} | {t["schema_name"] for t in found["tables"]}
    found["schemas"] = [{"schema_name": s} for s in sorted(names)]

    records = [dataset, *description.tables]
    licenses = {e["id"]: e for r in records for e in r.get("licenses") or []}
    found["licenses"] = [
        {"id": i, **_entry(e, ("url", "title", "commercial_use", "share_alike", "attribution_required"), language)}
        for i, e in sorted(licenses.items())
    ]
    sources = {e["id"]: e for r in records for e in r.get("sources") or []}
    found["sources"] = [{"id": i, **_entry(e, ("title", "url"), language)} for i, e in sorted(sources.items())]
    contributors = dataset.get("contributors") or []
    found["contributors"] = [
        {"id": c["id"], **_entry(c, ("title", "url"), language), "position": i} for i, c in enumerate(contributors)
    ]
    found["contributor_roles"] = [
        {"contributor_id": c["id"], "role": r} for c in contributors for r in dict.fromkeys(c.get("roles") or [])
    ]
    found["files"] = [f.entry() for f in description.files]
    return found


def _said(table: dict[str, Any]) -> bool:
    """Whether an author described ``table``: more than the SQL dbt fills in."""
    record = {k: v for k, v in table.items() if k not in ("schema", "name", "documents")}
    return bool(table.get("documents")) or shape.described(record)


def hidden(table: dict[str, Any]) -> bool:
    """Whether a row of `tables` is hidden from lists and search."""
    return table.get("hidden") is True


# -- checking the rows -------------------------------------------------------------------

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date(value: Any) -> bool:
    if not (isinstance(value, str) and _DATE.match(value)):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _fits(value: Any, kind: str) -> bool:
    """Whether DuckDB can hold ``value`` in a column of type ``kind``."""
    if value is None:
        return True
    if kind == "BOOLEAN":
        return isinstance(value, bool)
    if kind in ("BIGINT", "INTEGER"):
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, str)


def unfit(found: Rows, schema: str = SCHEMA) -> list[tuple[str, str, str]]:
    """(where, column, type) of each value in ``found`` its column cannot hold.

    `issued` is any text in the JSON Schema; it has to be a date (YYYY-MM-DD) here.
    """
    wrong = []
    for table, records in found.items():
        columns, key = TABLES[table]
        for record in records:
            named = ".".join(str(record[k]) for k in key if record.get(k))
            where = f"{schema}.{table}" + (f" {named}" if named else "")
            for column, value in record.items():
                kind = columns.get(column)
                if kind is not None and not _fits(value, kind):
                    wrong.append((where, column, kind))
            if table == "dataset" and record.get("key") == "issued" and not _date(record.get("value")):
                wrong.append((f"{schema}.dataset issued", "value", "DATE"))
    return wrong


def dangling(found: Rows, schema: str = SCHEMA) -> list[str]:
    """Each row that refers to a row ``found`` does not have. The catalog has no foreign keys,
    so load checks them before it writes."""
    have = {
        "schemas": {("", "", "")} | {(r["schema_name"], "", "") for r in found["schemas"]},
        "tables": {("", "", "")} | {(r["schema_name"], r["table_name"], "") for r in found["tables"]},
        "columns": {(r["schema_name"], r["table_name"], r["column_name"]) for r in found["columns"]},
    }

    def target(r: dict[str, Any]) -> tuple[str, tuple[str, str, str]]:
        at = (r.get("schema_name", ""), r.get("table_name", ""), r.get("column_name", ""))
        return ("columns" if at[2] else "tables" if at[1] else "schemas"), at

    wrong = []
    for table in ("tables", "columns", "metrics", "descriptions", "topics", "synonyms",
                  "table_licenses", "table_sources", "table_areas", "table_dependencies"):
        for r in found[table]:
            kind, at = target(r)
            if table == "tables":
                kind, at = "schemas", (at[0], "", "")
            elif table in ("columns", "metrics"):
                kind, at = "tables", (at[0], at[1], "")
            if at not in have[kind]:
                wrong.append(f"{schema}.{table}: {'.'.join(p for p in at if p)} is not in {schema}.{kind}")
    for table, column, other in (
        ("table_licenses", "license_id", "licenses"),
        ("table_sources", "source_id", "sources"),
        ("contributor_roles", "contributor_id", "contributors"),
    ):
        ids = {r["id"] for r in found[other]}
        wrong += [f"{schema}.{table}: {r[column]} is not in {schema}.{other}" for r in found[table] if r[column] not in ids]
    paths = {r["path"] for r in found["files"]}
    wrong += [
        f"{schema}.dataset: image {r['value']} is not in {schema}.files"
        for r in found["dataset"]
        if r["key"] == "image" and r["value"] not in paths
    ]
    return wrong


# -- reading and writing the catalog -----------------------------------------------------


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def spelled_schema(con: Any, catalog: str, schema: str) -> str:
    """``schema`` as ``catalog`` spells it, when it has a schema of that name in another case."""
    found = con.execute(
        "SELECT schema_name FROM duckdb_schemas() WHERE database_name = ? AND lower(schema_name) = lower(?) "
        "ORDER BY schema_name = ? DESC LIMIT 1",
        [catalog, schema, schema],
    ).fetchone()
    return found[0] if found else schema


def relations(con: Any, catalog: str, schema: str = SCHEMA) -> tuple[set[Key], set[Key], dict[Key, dict[str, str]]]:
    """(tables, views, each one's columns and types) of ``catalog``, but those of a description's
    schema: ``schema``, and each schema that holds every table of `_EVERY_LOAD` (such as one an
    earlier load wrote into). Names match without regard to case."""
    found = con.execute(
        """
        SELECT schema_name, table_name, false FROM duckdb_tables() WHERE database_name = $1
        UNION ALL
        SELECT schema_name, view_name, true FROM duckdb_views() WHERE database_name = $1
        """,
        [catalog],
    ).fetchall()
    held: dict[str, set[str]] = {}
    for s, n, v in found:
        if not v:
            held.setdefault(s.lower(), set()).add(n.lower())
    skipped = {schema.lower()} | {s for s, names in held.items() if names >= _EVERY_LOAD}
    kept = [(s, n, v) for s, n, v in found if s.lower() not in skipped]
    columns: dict[Key, dict[str, str]] = {(s, n): {} for s, n, _ in kept}
    for s, n, name, kind in con.execute(
        "SELECT schema_name, table_name, column_name, data_type FROM duckdb_columns() WHERE database_name = ?",
        [catalog],
    ).fetchall():
        if (s, n) in columns:
            columns[(s, n)][name] = kind
    return {(s, n) for s, n, v in kept if not v}, {(s, n) for s, n, v in kept if v}, columns


def read(con: Any, catalog: str, schema: str = SCHEMA) -> Rows:
    """The rows of the tables of ``schema`` ``catalog`` holds, without NULL values; {} when none."""
    found = con.execute(
        "SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = ? AND lower(schema_name) = lower(?)",
        [catalog, schema],
    ).fetchall()
    result: Rows = {}
    for held_in, table in found:
        if table.lower() not in TABLES:
            continue
        cursor = con.execute(f"SELECT * FROM {catalog}.{quote(held_in)}.{quote(table)}")
        names = [d[0] for d in cursor.description]
        result[table.lower()] = [
            {n: _plain(v) for n, v in zip(names, row) if v is not None} for row in cursor.fetchall()
        ]
    return result


def _plain(value: Any) -> Any:
    """``value`` as JSON holds it: NULL fields of a STRUCT left out, dates as text."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def write(con: Any, catalog: str, found: Rows, schema: str = SCHEMA) -> None:
    """Make the tables of ``schema`` in ``catalog`` hold ``found`` and no other rows, in one transaction.

    Rows are added, changed and removed by their primary key, so a version
    changes only the cells that differ, and merges with others' changes by them.
    The tables an earlier tabledoc wrote and this one does not (`texts`) are dropped;
    any other table of ``schema``, the profile tables among them, is left as it is.
    """
    con.execute("BEGIN")
    try:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{quote(schema)}")
        with tempfile.TemporaryDirectory(prefix="tabledoc-") as tmp:
            for table, (columns, key) in TABLES.items():
                _write_table(con, catalog, schema, table, columns, key, found.get(table) or [], Path(tmp))
        for (table,) in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = ? AND lower(schema_name) = lower(?)",
            [catalog, schema],
        ).fetchall():
            if table.lower() in _EARLIER:
                con.execute(f"DROP TABLE {catalog}.{quote(schema)}.{quote(table)}")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


def _write_table(
    con: Any,
    catalog: str,
    schema: str,
    table: str,
    columns: dict[str, str],
    key: tuple[str, ...],
    records: list[dict[str, Any]],
    tmp: Path,
) -> None:
    target = f"{catalog}.{quote(schema)}.{quote(table)}"
    spec = ", ".join(f"{quote(c)} {t}" for c, t in columns.items())
    con.execute(f"CREATE TABLE IF NOT EXISTS {target} ({spec})")
    held = {
        name
        for (name,) in con.execute(
            "SELECT column_name FROM duckdb_columns() WHERE database_name = ? "
            "AND lower(schema_name) = lower(?) AND lower(table_name) = lower(?)",
            [catalog, schema, table],
        ).fetchall()
    }
    lowered = {c.lower() for c in held}
    for column, kind in columns.items():
        if column.lower() not in lowered:
            con.execute(f"ALTER TABLE {target} ADD COLUMN {quote(column)} {kind}")
    for column in sorted(c for c in held if c.lower() not in {k.lower() for k in columns}):
        # A column an earlier tabledoc wrote and this one does not.
        con.execute(f"ALTER TABLE {target} DROP COLUMN {quote(column)}")
    staged = f"tabledoc_{table}"
    names = ", ".join(quote(c) for c in columns)
    con.execute(f"CREATE OR REPLACE TEMP TABLE {staged} ({spec})")
    if records:
        path = tmp / f"{table}.json"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records), encoding="utf-8")
        typed = ", ".join(f"{_literal(c)}: {_literal(t)}" for c, t in columns.items())
        con.execute(
            f"INSERT INTO {staged} ({names}) SELECT {names} FROM read_json(?, "
            f"format = 'newline_delimited', columns = {{{typed}}})",
            [path.as_posix()],
        )
    same_key = " AND ".join(f"t.{quote(k)} = s.{quote(k)}" for k in key)
    others = [c for c in columns if c not in key]
    con.execute(f"DELETE FROM {target} t WHERE NOT EXISTS (SELECT 1 FROM {staged} s WHERE {same_key})")
    if others:
        assigned = ", ".join(f"{quote(c)} = s.{quote(c)}" for c in others)
        differs = " OR ".join(f"t.{quote(c)} IS DISTINCT FROM s.{quote(c)}" for c in others)
        con.execute(f"UPDATE {target} t SET {assigned} FROM {staged} s WHERE {same_key} AND ({differs})")
    con.execute(
        f"INSERT INTO {target} ({names}) SELECT {names} FROM {staged} s "
        f"WHERE NOT EXISTS (SELECT 1 FROM {target} t WHERE {same_key})"
    )
    con.execute(f"DROP TABLE {staged}")
