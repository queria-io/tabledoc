"""A description written into a DuckLake catalog, as the tables of the `_meta` schema.

    _meta.dataset   one row: the dataset's title, description, licenses...
    _meta.schemas   one row per schema described          key: schema
    _meta.tables    one row per table or view             key: schema, name
    _meta.columns   one row per column described          key: schema, table, name
    _meta.files     the guides and documents              key: path
                    (sha256 holds an asset: the file itself is kept by content)

The tables are dropped and written again each time, in one transaction. The
descriptions of tables, views and columns are also written as DuckDB comments
(`COMMENT ON`), so `DESCRIBE` and `duckdb_tables()` show them; `_meta` is
where they come from. Readers ignore columns they do not know.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .description import README, Description
from .shape import BUILT_KEYS, QUERIA

SCHEMA = "_meta"

_LICENSE = (
    "STRUCT(id VARCHAR, spdx VARCHAR, url VARCHAR, title VARCHAR, "
    "commercial_use BOOLEAN, share_alike BOOLEAN, attribution_required BOOLEAN)[]"
)
_SOURCE = "STRUCT(title VARCHAR, path VARCHAR)[]"
_CONTRIBUTOR = "STRUCT(title VARCHAR, path VARCHAR, roles VARCHAR[])[]"
_TEMPORAL = 'STRUCT(start VARCHAR, "end" VARCHAR)'
_AI = "STRUCT(instructions VARCHAR, synonyms VARCHAR[], examples VARCHAR[])"

#: Each table: its columns and types, in order, and its primary key.
TABLES: dict[str, tuple[dict[str, str], list[str]]] = {
    "dataset": (
        {
            "title": "VARCHAR",
            "title_kana": "VARCHAR",
            "description": "VARCHAR",
            "language": "VARCHAR",
            "keywords": "VARCHAR[]",
            "homepage": "VARCHAR",
            "issued": "DATE",
            "update_frequency": "VARCHAR",
            "licenses": _LICENSE,
            "sources": _SOURCE,
            "contributors": _CONTRIBUTOR,
            "temporal_coverage": _TEMPORAL,
            "spatial_coverage": "VARCHAR[]",
            "themes": "VARCHAR[]",
            "cover": "VARCHAR",
            "ai_context": _AI,
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
            "keywords": "VARCHAR[]",
            "published": "BOOLEAN",
            "licenses": _LICENSE,
            "sources": _SOURCE,
            "themes": "VARCHAR[]",
            "temporal_coverage": _TEMPORAL,
            "spatial_coverage": "VARCHAR[]",
            "ai_context": _AI,
            "materialized": "VARCHAR",
            "sql": "VARCHAR",
            "depends_on": "VARCHAR[]",
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
        },
        ["schema", "table", "name"],
    ),
    "files": (
        {
            "path": "VARCHAR",
            "sha256": "VARCHAR",
            "bytes": "BIGINT",
            "media_type": "VARCHAR",
            "kind": "VARCHAR",
            "schema": "VARCHAR",
            "table": "VARCHAR",
            "position": "INTEGER",
            "title": "VARCHAR",
        },
        ["path"],
    ),
}
#: The column of _meta.files that holds an asset.
FILES_ASSET = "sha256"
#: Keys written under `queria:`, by level, that `_meta` has columns for.
EXTENSIONS = {
    "dataset": ("title_kana", "themes", "cover", "ai_context"),
    "table": ("published", "themes", "ai_context"),
}

Rows = dict[str, list[dict[str, Any]]]
Key = tuple[str, str]


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _pick(record: dict[str, Any], columns: tuple[str, ...] | list[str]) -> dict[str, Any]:
    return {c: record[c] for c in columns if _present(record.get(c))}


def _extensions(record: dict[str, Any], level: str) -> dict[str, Any]:
    own = (record.get("annotations") or {}).get(QUERIA) or {}
    return _pick(own, EXTENSIONS[level]) if isinstance(own, dict) else {}


def _licenses(value: Any) -> list[dict[str, Any]] | None:
    """Licenses as written: an id alone, or the id with its terms."""
    if not isinstance(value, list):
        return None
    return [{"id": v} if isinstance(v, str) else v for v in value if isinstance(v, (str, dict))] or None


def _record(record: dict[str, Any], columns: list[str], level: str) -> dict[str, Any]:
    picked = {**_pick(record, columns), **_extensions(record, level)}
    licenses = _licenses(record.get("licenses"))
    return {**picked, **({"licenses": licenses} if licenses else {})}


def _entity(column: dict[str, Any]) -> str | None:
    entity = column.get("entity")
    return entity.get("name") if isinstance(entity, dict) else None


def _kinds(description: Description) -> dict[str, dict[str, Any]]:
    """What each file of ``description.files`` is: a guide (of what), a doc (where), or nothing."""
    found: dict[str, dict[str, Any]] = {}
    for table in description.tables:
        if table.get("guide"):
            found[table["guide"]] = {"kind": "guide", "schema": table["schema"], "table": table["name"]}
    for schema in description.schemas:
        if schema.get("guide"):
            found.setdefault(schema["guide"], {"kind": "guide", "schema": schema["name"]})
    for position, path in enumerate(description.dataset.get("docs") or []):
        found.setdefault(path, {"kind": "doc", "position": position})
    if description.dataset.get("guide") == README:
        found.setdefault(README, {"kind": "guide"})
    return found


def rows(description: Description, carried: Rows | None = None, unlisted: set[Key] | None = None) -> Rows:
    """The rows of each `_meta` table for ``description``.

    ``carried`` is the `_meta` the catalog held: a table without `sql` and
    `depends_on` (nothing was built) keeps them from it. ``unlisted`` are
    tables with no description, written as not published.
    """
    columns = {name: list(spec[0]) for name, spec in TABLES.items()}
    kept = {(t["schema"], t["name"]): t for t in (carried or {}).get("tables") or []}
    described = {fold(t["schema"], t["name"]) for t in description.tables}
    tables = [
        {
            "schema": t["schema"],
            "name": t["name"],
            **_pick(kept.get((t["schema"], t["name"]), {}), BUILT_KEYS),
            **_record(t, columns["tables"][2:], "table"),
        }
        for t in description.tables
    ] + [
        {"schema": s, "name": n, "published": False}
        for s, n in sorted(unlisted or set())
        if fold(s, n) not in described
    ]
    kinds = _kinds(description)
    return {
        "dataset": [_record(description.dataset, columns["dataset"], "dataset")],
        "schemas": [
            {"schema": s["name"], **_pick(s, ["title", "description"])}
            for s in description.schemas
            if s.get("name")
        ],
        "tables": tables,
        "columns": [
            {
                "schema": t["schema"],
                "table": t["name"],
                "name": c["name"],
                **_pick({**c, "entity": _entity(c)}, ["title", "description", "entity"]),
            }
            for t in description.tables
            for c in t.get("columns") or []
            if c.get("name") and (c.get("title") or c.get("description") or _entity(c))
        ],
        "files": [{**f.entry(), **kinds.get(f.path, {})} for f in description.files],
    }


def structure(description: Description) -> dict[str, Any]:
    """What `fdl commit --dataset` takes: the primary keys and asset columns, and no description.

    fdl writes them as the tags `fdl.primary_key`, `fdl.assets` and
    `fdl.catalogs`. The `_meta` tables get their keys, and `_meta.files.sha256`
    is an asset column.
    """
    tables = [
        {
            "schema": t["schema"],
            "name": t["name"],
            **({"primary_key": t["primary_key"]} if t.get("primary_key") else {}),
            **(
                {"fields": [{"name": c["name"], "asset": True} for c in assets]}
                if (assets := [c for c in t.get("columns") or [] if c.get("asset") is True])
                else {}
            ),
        }
        for t in description.tables
    ]
    meta = [
        {
            "schema": SCHEMA,
            "name": table,
            **({"primary_key": key} if key else {}),
            **({"fields": [{"name": FILES_ASSET, "asset": True}]} if table == "files" else {}),
        }
        for table, (_, key) in TABLES.items()
    ]
    return {
        "name": description.dataset.get("name"),
        **({"catalogs": description.catalogs} if description.catalogs else {}),
        "tables": [t for t in tables if set(t) - {"schema", "name"}] + meta,
    }


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fits(value: Any, kind: str) -> bool:
    """Whether DuckDB can read ``value`` as a column of type ``kind`` (its outer shape)."""
    if value is None:
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
    """(where, column, type) of each value in ``found`` its `_meta` column cannot hold.

    tabledoc does not check the keys under `queria:`, and `issued` is any text
    in the schema; DuckDB refuses them here unless they have the column's type.
    """
    wrong = []
    for table, records in found.items():
        columns = TABLES[table][0]
        for record in records:
            key = ".".join(str(record[k]) for k in TABLES[table][1] if k in record)
            where = f"{SCHEMA}.{table}" + (f" {key}" if key else "")
            for column, value in record.items():
                kind = columns.get(column)
                if kind is not None and not _fits(value, kind):
                    wrong.append((where, column, kind))
    return wrong


def fold(*names: str) -> tuple[str, ...]:
    """``names`` as DuckDB compares identifiers: without regard to case."""
    return tuple(n.lower() for n in names)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: str | None) -> str:
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


def write(con: Any, catalog: str, found: Rows) -> None:
    """Write ``found`` as the `_meta` tables of ``catalog`` (attached on ``con``), and the comments.

    In one transaction: a row DuckDB refuses (a date out of range, say) leaves
    the catalog as it was.
    """
    con.execute("BEGIN")
    try:
        _write(con, catalog, found)
        _comment(con, catalog, found)
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


def _write(con: Any, catalog: str, found: Rows) -> None:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{SCHEMA}")
    with tempfile.TemporaryDirectory(prefix="tabledoc-meta-") as tmp:
        for table, (columns, _) in TABLES.items():
            target = f"{catalog}.{SCHEMA}.{_quote(table)}"
            con.execute(f"DROP TABLE IF EXISTS {target}")
            spec = ", ".join(f"{_quote(c)} {t}" for c, t in columns.items())
            con.execute(f"CREATE TABLE {target} ({spec})")
            records = found.get(table) or []
            if not records:
                continue
            path = Path(tmp) / f"{table}.json"
            path.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records), encoding="utf-8"
            )
            typed = ", ".join(f"'{c}': {_literal(t)}" for c, t in columns.items())
            names = ", ".join(_quote(c) for c in columns)
            con.execute(
                f"INSERT INTO {target} ({names}) SELECT {names} FROM read_json(?, "
                f"format = 'newline_delimited', columns = {{{typed}}})",
                [path.as_posix()],
            )


def _comment(con: Any, catalog: str, found: Rows) -> None:
    """Each table's, view's and column's comment as `_meta` describes it; cleared when it does not.

    A view's columns get none: DuckDB takes no `COMMENT ON COLUMN` for a view.
    Names match without regard to case, as DuckDB's identifiers do.
    """
    tables = {fold(t["schema"], t["name"]): t.get("description") for t in found.get("tables") or []}
    columns = {fold(c["schema"], c["table"], c["name"]): c.get("description") for c in found.get("columns") or []}
    relations = con.execute(
        """
        SELECT schema_name, table_name, comment, 'TABLE' FROM duckdb_tables() WHERE database_name = $1
        UNION ALL
        SELECT schema_name, view_name, comment, 'VIEW' FROM duckdb_views() WHERE database_name = $1
        """,
        [catalog],
    ).fetchall()
    for schema, name, held, kind in relations:
        wanted = tables.get(fold(schema, name))
        if schema != SCHEMA and held != wanted:
            con.execute(f"COMMENT ON {kind} {catalog}.{_quote(schema)}.{_quote(name)} IS {_literal(wanted)}")
    held_columns = con.execute(
        """
        SELECT c.schema_name, c.table_name, c.column_name, c.comment
        FROM duckdb_columns() c JOIN duckdb_tables() t
          ON t.database_name = c.database_name AND t.schema_name = c.schema_name AND t.table_name = c.table_name
        WHERE c.database_name = ? AND c.schema_name <> ?
        """,
        [catalog, SCHEMA],
    ).fetchall()
    for schema, table, name, held in held_columns:
        wanted = columns.get(fold(schema, table, name))
        if held != wanted:
            target = ".".join([catalog, *map(_quote, (schema, table, name))])
            con.execute(f"COMMENT ON COLUMN {target} IS {_literal(wanted)}")


def read(con: Any, catalog: str) -> Rows | None:
    """The `_meta` tables ``catalog`` holds, or None when it has none."""
    found = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = ? AND schema_name = ?",
        [catalog, SCHEMA],
    ).fetchall()
    if not found:
        return None
    present = {name for (name,) in found}
    result: Rows = {}
    for table in TABLES:
        if table in present:
            cursor = con.execute(f"SELECT * FROM {catalog}.{SCHEMA}.{_quote(table)}")
            names = [d[0] for d in cursor.description]
            result[table] = [dict(zip(names, row)) for row in cursor.fetchall()]
    return result


def relations(con: Any, catalog: str) -> set[Key]:
    """The tables and views of ``catalog``, but `_meta`'s."""
    found = con.execute(
        """
        SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = $1
        UNION ALL
        SELECT schema_name, view_name FROM duckdb_views() WHERE database_name = $1
        """,
        [catalog],
    ).fetchall()
    return {(s, n) for s, n in found if s != SCHEMA}


def write_assets(description: Description, out: Path, linked: Path | None) -> None:
    """The files `fdl commit --assets out` uploads.

    Each file under ``out/files/<path>``, its extension kept so the upload
    carries its media type. fdl leaves hidden files and folders out, so a file
    with a hidden part in its path goes to ``out/files/<sha256><suffix>``: fdl
    finds assets by content. With ``linked`` (the build's own assets), every
    file below it is linked under ``out/data/`` so one folder holds both.
    """
    for file in description.files:
        path = PurePosixPath(file.path)
        hidden = any(part.startswith(".") for part in path.parts)
        target = out / "files" / (file.sha256 + path.suffix if hidden else path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(description.content(file))
    if linked is None:
        return
    base = linked.resolve()
    for folder, _, names in os.walk(base, followlinks=True):
        for name in names:
            source = Path(folder) / name
            target = out / "data" / source.relative_to(base)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(source)
