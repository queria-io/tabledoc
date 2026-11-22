"""A description as the rows of the `_fdl` schema, which FDL defines (https://fdl.queria.io/spec/fdl-schema).

    _fdl.dataset      one row: the dataset's title, description, licenses...
    _fdl.schemas      one row per schema described          key: schema
    _fdl.tables       one row per table or view             key: schema, name
    _fdl.columns      one row per column described          key: schema, table, name
    _fdl.files        the documents and what they link to   key: path
    _fdl.catalogs     the other datasets the views read     key: name
    _fdl.attributes   keys for one reader                   key: schema, table, column, key

tabledoc builds the rows; fdl writes and checks them. Every read and write of
`_fdl` goes through the fdl CLI (`fdl meta dump`, `fdl meta objects`,
`fdl meta set --replace --stdin`), so `_fdl` is defined in one place.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .description import Description
from .report import SpecError
from .shape import BUILT_KEYS, QUERIA

SCHEMA = "_fdl"

#: The license's terms, written as Queria's `license_terms` by license id.
LICENSE_TERMS = ("commercial_use", "share_alike", "attribution_required")
DBT = "dbt"
#: What dbt fills in that FDL has no column for, written as dbt's attributes.
DBT_KEYS = ("materialized", "source_path")

_COVERAGE = ["licenses", "sources", "temporal_coverage", "spatial_coverage"]
#: The columns of `_fdl.dataset` and `_fdl.tables` a description fills in.
DATASET_COLUMNS = ["title", "description", "language", "homepage", "issued", "update_frequency", *_COVERAGE, "contributors"]
TABLE_COLUMNS = ["title", "description", *_COVERAGE, "primary_key", "sql", "depends_on"]

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
    return [
        {"id": v} if isinstance(v, str) else {k: x for k, x in v.items() if k not in LICENSE_TERMS}
        for v in value
        if isinstance(v, (str, dict))
    ] or None


def _license_terms(value: Any) -> dict[str, Any]:
    """License id -> its terms, for the licenses written with them."""
    return {
        v["id"]: terms
        for v in (value if isinstance(value, list) else [])
        if isinstance(v, dict) and v.get("id") and (terms := {k: v[k] for k in LICENSE_TERMS if k in v})
    }


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


#: Keys under `queria:` that Queria no longer reads, so they are not written.
DROPPED = {QUERIA: ("themes",)}


def readers(record: dict[str, Any]) -> dict[str, Any]:
    """The keys of each reader for ``record``: its `annotations`, with `topics` as Queria's
    `topics` unless `queria:` says them, and without the keys in ``DROPPED``."""
    found = {r: dict(k) for r, k in (record.get("annotations") or {}).items() if isinstance(k, dict)}
    own = {
        "topics": record.get("topics"),
        "license_terms": _license_terms(record.get("licenses")),
        "entity": _entity(record),
    }
    for key, value in own.items():
        if value:
            found.setdefault(QUERIA, {}).setdefault(key, value)
    for key in DBT_KEYS:
        if record.get(key):
            found.setdefault(DBT, {})[key] = record[key]
    for reader, keys in DROPPED.items():
        for key in keys:
            found.get(reader, {}).pop(key, None)
    return {r: k for r, k in found.items() if k}


def _attributes(record: dict[str, Any], schema: str = "", table: str = "", column: str = "") -> list[dict[str, Any]]:
    """One row per key of each reader (`queria:` among them)."""
    readers_ = readers(record)
    return [
        {"schema": schema, "table": table, "column": column, "key": attribute_key(reader, key), "value": value}
        for reader, keys in readers_.items()
        for key, value in keys.items()
    ]


def _built(carried: Rows) -> dict[tuple[str, ...], dict[str, Any]]:
    """What the build filled in for each table, as the catalog held it: `sql` and
    `depends_on` from `_fdl.tables`, `materialized` and `source_path` from dbt's
    attributes (or, in `_meta`, from its columns)."""
    found: dict[tuple[str, ...], dict[str, Any]] = {}
    for t in carried.get("tables") or []:
        found[fold(t["schema"], t["name"])] = _pick(t, BUILT_KEYS)
    for a in carried.get("attributes") or []:
        reader, key = split_key(a["key"])
        if reader == DBT and key in DBT_KEYS and a.get("table") and not a.get("column"):
            found.setdefault(fold(a.get("schema", ""), a["table"]), {})[key] = a["value"]
    return found


def built_by_dbt(carried: Rows) -> bool:
    """Whether the catalog holds a table dbt built, as its `dbt-source-path` says."""
    return any(built.get("source_path") for built in _built(carried or {}).values())


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
    was built) keeps `sql`, `depends_on` and dbt's `materialized` and
    `source_path` from it. ``unlisted`` are the catalog's tables with no description: Queria does
    not list them and they get no profile. ``views`` are the catalog's views,
    whose SQL the metadata already holds.
    """
    built = not carried or any("sql" in t for t in description.tables)
    kept = {} if built else _built(carried or {})
    described = {fold(t["schema"], t["name"]) for t in description.tables}
    viewed = {fold(*v) for v in views or set()}
    no_profile = {"profile": False}
    tables = [{**_pick(kept.get(fold(t["schema"], t["name"]), {}), BUILT_KEYS), **t} for t in description.tables]

    def table(t: dict[str, Any]) -> dict[str, Any]:
        record = _record(t, TABLE_COLUMNS)
        if fold(t["schema"], t["name"]) in viewed:
            record.pop("sql", None)
        return {"schema": t["schema"], "name": t["name"], **record, **({} if published(t) else no_profile)}

    unlisted_keys = [(s, n) for s, n in sorted(unlisted or set()) if fold(s, n) not in described]
    return {
        "dataset": [d] if (d := _record(description.dataset, DATASET_COLUMNS)) else [],
        "schemas": [
            {"schema": s["name"], **_pick(s, ["title", "description"])}
            for s in description.schemas
            if s.get("title") or s.get("description")
        ],
        "tables": [table(t) for t in tables]
        + [{"schema": s, "name": n, **no_profile} for s, n in unlisted_keys],
        "columns": [
            {
                "schema": t["schema"],
                "table": t["name"],
                "name": c["name"],
                **_pick(c, ["title", "description"]),
                **({"asset": True} if c.get("asset") is True else {}),
            }
            for t in description.tables
            for c in t.get("columns") or []
            if c.get("name") and (c.get("title") or c.get("description") or c.get("asset") is True)
        ],
        "files": [f.entry() for f in description.files],
        "catalogs": [{"name": k, "url": v} for k, v in sorted((description.catalogs or {}).items())],
        "attributes": _attributes(description.dataset)
        + [a for t in tables for a in _attributes(t, t["schema"], t["name"])]
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


def _command() -> list[str]:
    """The fdl CLI: the one installed beside this Python (fdl-cli is a dependency), else on PATH."""
    beside = Path(sys.executable).with_name("fdl")
    found = str(beside) if beside.is_file() else shutil.which("fdl")
    if found is None:
        raise SpecError("cannot find the fdl command; install fdl-cli")
    return [found]


def _run(*args: str, given: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*_command(), "meta", *args], input=given, capture_output=True, text=True, encoding="utf-8")


def _failed(done: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(line.removeprefix("error: ") for line in done.stderr.strip().splitlines()) or f"fdl exited with {done.returncode}"


def _json(*args: str) -> Any:
    done = _run(*args)
    if done.returncode != 0:
        raise SpecError(f"fdl meta {args[0]}: {_failed(done)}")
    return json.loads(done.stdout)


def dump(working: str) -> Rows:
    """Every row of `_fdl` in ``working`` (`fdl meta dump`), without NULL values."""
    return _json("dump", working)


def objects(working: str) -> tuple[set[Key], set[Key], dict[Key, dict[str, str]]]:
    """(tables, views, each table's columns and types) of ``working`` (`fdl meta objects`)."""
    found = _json("objects", working)
    tables = {(o["schema"], o["name"]) for o in found if o["kind"] == "table"}
    views = {(o["schema"], o["name"]) for o in found if o["kind"] == "view"}
    columns = {(o["schema"], o["name"]): {c["name"]: c["type"] for c in o.get("columns") or []} for o in found}
    return tables, views, columns


def load(working: str, found: Rows) -> str | None:
    """Make `_fdl` of ``working`` hold ``found`` and nothing else (`fdl meta set --replace --stdin`).

    None when written; else fdl's reason, and nothing is written.
    """
    done = _run("set", working, "--replace", "--stdin", given=json.dumps(found, ensure_ascii=False, default=str))
    return None if done.returncode == 0 else _failed(done)
