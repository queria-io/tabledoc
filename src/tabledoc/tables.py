"""A description as the rows of the tables of one schema: `_tabledoc` by default, `_queria` for Queria.

    dataset   one row, id 'dataset': its language, licenses...  key: id
    schemas   one row per schema described          key: schema
    tables    one row per table or view             key: schema, name
    columns   one row per column described          key: schema, table, name
    texts     title, description and topics of each, one row per language
                                                    key: schema, table, column, language
    files     the documents and what they link to   key: path

They are ordinary tables of the catalog, versioned with the data. FDL does not
know what they mean; `files.sha256` is declared to it as an asset column.
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
from .shape import BUILT_KEYS, QUERIA

SCHEMA = "_tabledoc"

_LICENSE = (
    "STRUCT(id VARCHAR, spdx VARCHAR, url VARCHAR, title VARCHAR, "
    "commercial_use BOOLEAN, share_alike BOOLEAN, attribution_required BOOLEAN)[]"
)
_COVERAGE = {
    "licenses": _LICENSE,
    "sources": "STRUCT(title VARCHAR, path VARCHAR)[]",
    "temporal_coverage": 'STRUCT("start" VARCHAR, "end" VARCHAR)',
    "spatial_coverage": "VARCHAR[]",
}

#: Each table: its columns and types, in order, and its primary key.
TABLES: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    "dataset": (
        {
            "id": "VARCHAR",
            "title_kana": "VARCHAR",
            "language": "VARCHAR",
            "homepage": "VARCHAR",
            "repository": "VARCHAR",
            "issued": "DATE",
            "update_frequency": "VARCHAR",
            "licenses": _LICENSE,
            "sources": _COVERAGE["sources"],
            "contributors": "STRUCT(title VARCHAR, path VARCHAR, roles VARCHAR[])[]",
            "temporal_coverage": _COVERAGE["temporal_coverage"],
            "spatial_coverage": "VARCHAR[]",
            "cover": "VARCHAR",
            "ai_context": "JSON",
        },
        ("id",),
    ),
    "schemas": ({"schema": "VARCHAR"}, ("schema",)),
    "tables": (
        {
            "schema": "VARCHAR",
            "name": "VARCHAR",
            **_COVERAGE,
            "published": "BOOLEAN",
            "ai_context": "JSON",
            "sql": "VARCHAR",
            "depends_on": "VARCHAR[]",
            "source_path": "VARCHAR",
        },
        ("schema", "name"),
    ),
    "columns": (
        {
            "schema": "VARCHAR",
            "table": "VARCHAR",
            "name": "VARCHAR",
            "entity": "VARCHAR",
        },
        ("schema", "table", "name"),
    ),
    "texts": (
        {
            "schema": "VARCHAR",
            "table": "VARCHAR",
            "column": "VARCHAR",
            "language": "VARCHAR",
            "title": "VARCHAR",
            "description": "VARCHAR",
            "topics": "VARCHAR[]",
        },
        ("schema", "table", "column", "language"),
    ),
    "files": (
        {"path": "VARCHAR", "sha256": "VARCHAR", "bytes": "BIGINT", "media_type": "VARCHAR"},
        ("path",),
    ),
}

#: The `id` of the one row of `_tabledoc.dataset`.
DATASET_ID = "dataset"
#: Asset columns of `_tabledoc` itself, declared to FDL.
ASSETS = {"files": ("sha256",)}
#: What `queria:` may say, as columns: of the dataset, and of a table.
DATASET_OWN = ("title_kana", "cover", "ai_context")
TABLE_OWN = ("published", "ai_context")
#: The columns of `texts` that hold text, one language a row.
TEXTS = ("title", "description", "topics")

Rows = dict[str, list[dict[str, Any]]]
Key = tuple[str, str]


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _pick(record: dict[str, Any], columns: Any) -> dict[str, Any]:
    return {c: record[c] for c in columns if _present(record.get(c))}


def _own(record: dict[str, Any]) -> dict[str, Any]:
    """What `queria:` (under `annotations`) says of ``record``."""
    own = (record.get("annotations") or {}).get(QUERIA)
    return own if isinstance(own, dict) else {}


def _licenses(value: Any) -> list[dict[str, Any]] | None:
    """Licenses as written: an id alone, or the id with its url, title and terms."""
    if not isinstance(value, list):
        return None
    return [{"id": v} if isinstance(v, str) else dict(v) for v in value if isinstance(v, (str, dict))] or None


def _queria_keys(record: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """The keys of ``queria:`` that are columns."""
    own = _own(record)
    return {k: own[k] for k in keys if k in own and own[k] is not None}


def _single(value: Any, language: str) -> Any:
    """``value`` with each text in ``language`` alone (see ``languages.one``)."""
    if isinstance(value, dict):
        return languages.one(value, language)
    if isinstance(value, list):
        return [{k: languages.one(v, language) for k, v in e.items()} if isinstance(e, dict) else e for e in value]
    return value


def _record(
    record: dict[str, Any], columns: dict[str, str], own: tuple[str, ...], language: str
) -> dict[str, Any]:
    licenses = _licenses(record.get("licenses"))
    texts = ("homepage", *languages.LISTS)
    picked = _pick(record, [c for c in columns if c not in own and c != "licenses"])
    return {
        **{k: _single(v, language) if k in texts else v for k, v in picked.items()},
        **({"licenses": _single(licenses, language)} if licenses else {}),
        **_queria_keys(record, own),
    }


def _texts(record: dict[str, Any], where: tuple[str, str, str], language: str) -> list[dict[str, Any]]:
    """The rows of `texts` for ``record`` at (schema, table, column), one per language.

    `topics` under `queria:` wins over the record's own.
    """
    topics = _own(record).get("topics")
    values = {
        **{k: record[k] for k in TEXTS if isinstance(record.get(k), dict)},
        **({"topics": languages.as_map(topics, language)} if topics else {}),
    }
    tags = sorted({tag for value in values.values() if value for tag in value})
    schema, table, column = where
    return [
        {
            "schema": schema,
            "table": table,
            "column": column,
            "language": tag,
            **{k: value[tag] for k, value in values.items() if value and tag in value},
        }
        for tag in tags
    ]


def several(description: Description) -> list[str]:
    """Where text outside `texts` is written in more than one language: only the one in
    `language` is written. As ``<where>: <key>``."""
    found = []

    def look(where: str, record: dict[str, Any]) -> None:
        for key, value in record.items():
            if key == "homepage" and languages.several(value):
                found.append(f"{where}: {key}")
            if key in languages.LISTS and isinstance(value, list):
                found.extend(
                    f"{where}: {key}.{k}"
                    for e in value
                    if isinstance(e, dict)
                    for k, v in e.items()
                    if languages.several(v)
                )

    look("dataset", description.dataset)
    for t in description.tables:
        look(f"{t['schema']}.{t['name']}", t)
    return found


def _entity(column: dict[str, Any]) -> str | None:
    entity = column.get("entity")
    return entity.get("name") if isinstance(entity, dict) else None


def fold(*names: str) -> tuple[str, ...]:
    """``names`` as DuckDB compares identifiers: without regard to case."""
    return tuple(n.lower() for n in names)


def rows(
    description: Description,
    carried: Rows | None = None,
    unlisted: set[Key] | None = None,
    views: set[Key] | None = None,
) -> Rows:
    """The rows of each `_tabledoc` table for ``description``.

    ``carried`` is the `_tabledoc` the catalog held: without a dbt build (no `sql`
    in the description), each table keeps `sql`, `depends_on` and `source_path`
    from it. ``unlisted`` are the catalog's tables and views:
    those with no description, and those dbt built that say nothing but their
    SQL, are written as not published. ``views`` are the
    catalog's views, whose SQL the metadata already holds.
    """
    columns = {name: {c: t for c, t in spec[0].items() if c != "id"} for name, spec in TABLES.items()}
    built = not carried or any("sql" in t for t in description.tables)
    kept = {} if built else {fold(t["schema"], t["name"]): _pick(t, BUILT_KEYS) for t in carried.get("tables") or []}
    described = {fold(t["schema"], t["name"]) for t in description.tables}
    viewed = {fold(*v) for v in views or set()}
    table_columns = {c: t for c, t in columns["tables"].items() if c not in ("schema", "name")}

    # `repository` from tabledoc.yml, else Git's origin; `source_path` from its root.
    where = description.source or {}
    folder = where.get("path") or ""
    dataset = description.dataset
    language = str(dataset.get("language") or languages.UNDETERMINED)
    if not dataset.get("repository") and where.get("repository"):
        dataset = {**dataset, "repository": where["repository"]}

    def table(t: dict[str, Any]) -> dict[str, Any]:
        if t.get("source_path") and folder:
            t = {**t, "source_path": f"{folder}/{t['source_path']}"}
        merged = {**kept.get(fold(t["schema"], t["name"]), {}), **t}
        record = _record(merged, table_columns, TABLE_OWN, language)
        if unlisted is not None and not _said(t) and record.get("published") is None:
            record["published"] = False
        if fold(t["schema"], t["name"]) in viewed:
            # The metadata holds a view's SQL, and so what it reads.
            record.pop("sql", None)
            record.pop("depends_on", None)
        return {"schema": t["schema"], "name": t["name"], **record}

    unlisted_keys = [(s, n) for s, n in sorted(unlisted or set()) if fold(s, n) not in described]
    return {
        "dataset": [{"id": DATASET_ID, **_record(dataset, columns["dataset"], DATASET_OWN, language)}],
        "schemas": [{"schema": s["name"]} for s in description.schemas if s.get("title") or s.get("description")],
        "tables": [table(t) for t in description.tables]
        + [table({"schema": s, "name": n}) for s, n in unlisted_keys],
        "columns": [
            {
                "schema": t["schema"],
                "table": t["name"],
                "name": c["name"],
                **({"entity": e} if (e := _entity(c)) else {}),
            }
            for t in description.tables
            for c in t.get("columns") or []
            if c.get("name") and (c.get("title") or c.get("description") or _entity(c))
        ],
        "texts": [
            *_texts(dataset, ("", "", ""), language),
            *(r for s in description.schemas for r in _texts(s, (s["name"], "", ""), language)),
            *(r for t in description.tables for r in _texts(t, (t["schema"], t["name"], ""), language)),
            *(
                r
                for t in description.tables
                for c in t.get("columns") or []
                if c.get("name")
                for r in _texts(c, (t["schema"], t["name"], c["name"]), language)
            ),
        ],
        "files": [f.entry() for f in description.files],
    }


def _said(table: dict[str, Any]) -> bool:
    """Whether an author described ``table``: more than the SQL dbt fills in."""
    record = {k: v for k, v in table.items() if k not in ("schema", "name", "guide", "docs")}
    return bool(table.get("guide") or table.get("docs")) or shape.described(record)


def published(table: dict[str, Any]) -> bool:
    """Whether Queria lists a table: unless its `published` is false."""
    return table.get("published") is not False


# -- checking the values -----------------------------------------------------------------

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
    if kind == "BIGINT":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def unfit(found: Rows, schema: str = SCHEMA) -> list[tuple[str, str, str]]:
    """(where, column, type) of each value in ``found`` its column cannot hold.

    `issued` is any text in the JSON Schema; DuckDB refuses it here unless it is a date.
    """
    wrong = []
    for table, records in found.items():
        columns, key = TABLES[table]
        for record in records:
            named = ".".join(str(record[k]) for k in key if record.get(k) and k != "id")
            where = f"{schema}.{table}" + (f" {named}" if named else "")
            for column, value in record.items():
                kind = columns.get(column)
                if kind is not None and not _fits(value, kind):
                    wrong.append((where, column, kind))
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
    schema: ``schema``, and each schema that holds every table of `TABLES` (such as one an
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
    skipped = {schema.lower()} | {s for s, names in held.items() if names >= set(TABLES)}
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
    """The rows of the tables of ``schema`` ``catalog`` holds, without NULL values; {} when none.

    Values of a JSON column come back parsed.
    """
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
        kinds = TABLES[table.lower()][0]
        result[table.lower()] = [
            {
                n: json.loads(v) if kinds.get(n) == "JSON" and isinstance(v, str) else _plain(v)
                for n, v in zip(names, row)
                if v is not None
            }
            for row in cursor.fetchall()
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
    """
    con.execute("BEGIN")
    try:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{quote(schema)}")
        with tempfile.TemporaryDirectory(prefix="tabledoc-") as tmp:
            for table, (columns, key) in TABLES.items():
                _write_table(con, catalog, schema, table, columns, key, found.get(table) or [], Path(tmp))
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
