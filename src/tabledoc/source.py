"""Reads what an author wrote under the root (the folder of tabledoc.yml).

    tabledoc.yml                    the dataset
    README.md                       its overview
    <schema>/<table>.tabledoc.yml   a table, with tabledoc's table schema as $schema
    <schema>/<table>.md             that table's guide

In a dbt project, `<model>.tabledoc.yml` and `<model>.md` sit next to
`<model>.sql` and describe that model's table. A dbt project's tables come
from dbt (see dbt.py); this module reads the files.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from . import legacy, schemas
from .report import Report, SpecError

DATASET_FILE = "tabledoc.yml"
#: Folders never read: build output, dependencies, and hidden folders.
IGNORED_DIRS = frozenset({"target", "dbt_packages", "node_modules", ".venv"})
#: The file `tabledoc export --markdown` leaves in its folder; a folder holding it is not read either.
EXPORT_MARK = ".tabledoc-export"
DEFAULT_SCHEMA = "main"
#: The end of a table file's name: `<table>.tabledoc.yml`.
TABLE_SUFFIX = ".tabledoc.yml"

Key = tuple[str, str]


@dataclass(frozen=True)
class Table:
    """One table as an author described it, in the table file's form."""

    schema: str
    name: str
    record: dict[str, Any]
    #: The file it is described in.
    path: Path
    #: The guide, relative to the root, when there is one.
    guide: str | None = None

    @property
    def key(self) -> Key:
        return (self.schema, self.name)


@dataclass(frozen=True)
class Dataset:
    record: dict[str, Any]
    path: Path
    #: Name -> URL of the other datasets the SQL reads, from queria.yml `catalogs` (the older format only).
    dependencies: dict[str, str]


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def walk(root: Path, suffixes: tuple[str, ...]) -> Iterator[Path]:
    """Files under ``root`` ending in one of ``suffixes``, outside the folders never read
    and the folders `tabledoc export --markdown` wrote."""
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if entry.is_dir():
                if (
                    entry.name not in IGNORED_DIRS
                    and not entry.name.startswith(".")
                    and not (entry / EXPORT_MARK).is_file()
                ):
                    stack.append(entry)
            elif entry.name.endswith(suffixes):
                yield entry


def _yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"{path}: not valid YAML: {exc}") from exc


def _unknown(schema: Any, path: Path) -> SpecError:
    if isinstance(schema, str) and schema.startswith(schemas.MOVED_BASE):
        moved = schemas.BASE + schema[len(schemas.MOVED_BASE) :]
        return SpecError(f"{path}: $schema {schema} has moved; write {moved}")
    return SpecError(f"{path}: $schema {schema} is not one this tabledoc knows; upgrade tabledoc")


def read_dataset(root: Path, report: Report) -> Dataset:
    """tabledoc.yml, else queria.yml (the older format)."""
    current, older = root / DATASET_FILE, root / legacy.DATASET_FILE
    if current.is_file() and older.is_file():
        raise SpecError(f"{root}: both {DATASET_FILE} and {legacy.DATASET_FILE} are here; keep {DATASET_FILE}")
    path = current if current.is_file() else older if older.is_file() else None
    if path is None:
        raise SpecError(f"{root}: no {DATASET_FILE} here")
    record = _yaml(path)
    if not isinstance(record, dict):
        raise SpecError(f"{path}: the top level is not a mapping")
    expected = schemas.DATASET if path is current else schemas.LEGACY_DATASET
    if record.get("$schema") != expected:
        if record.get("$schema"):
            raise _unknown(record.get("$schema"), path)
        raise SpecError(f"{path}: $schema has to be {expected}")
    schemas.check(record, expected, path, report)
    if path is current:
        return Dataset(record={k: v for k, v in record.items() if k != "$schema"}, path=path, dependencies={})
    report.info("legacy-format", f"read as {DATASET_FILE}; rename it and move Queria's keys under queria:", path)
    converted = legacy.dataset({k: v for k, v in record.items() if k != "$schema"})
    dependencies = converted.pop("catalogs", None)
    return Dataset(record=converted, path=path, dependencies=dependencies if isinstance(dependencies, dict) else {})


def stem(path: Path) -> str:
    """The name a file is about: `series` for series.tabledoc.yml, series.sql and series.md."""
    return path.name[: -len(TABLE_SUFFIX)] if path.name.endswith(TABLE_SUFFIX) else path.name.rsplit(".", 1)[0]


def _table_key(root: Path, path: Path, models: dict[Path, Key], report: Report) -> Key | None:
    """Which table a table file describes: the model whose SQL is beside it, else its place under the root."""
    sql = path.with_name(stem(path) + ".sql")
    if sql in models:
        return models[sql]
    if sql.is_file():
        if models:
            report.error("table-without-model", f"{rel(root, sql)} beside it is not a model that makes a table", path)
        return None
    parts = PurePosixPath(rel(root, path)).parts
    if len(parts) == 1:
        return DEFAULT_SCHEMA, stem(path)
    if len(parts) == 2:
        return parts[0], stem(path)
    report.error(
        "table-unplaced", f"not at <schema>/<table>{TABLE_SUFFIX} or next to a model's .sql", path
    )
    return None


def sibling_guide(root: Path, path: Path) -> str | None:
    """The guide of the table described at ``path`` (its table file or its model's SQL): ``<name>.md`` beside it."""
    guide = path.with_name(stem(path) + ".md")
    return rel(root, guide) if guide.is_file() else None


def read_table_files(root: Path, report: Report, models: dict[Path, Key] | None = None) -> list[Table]:
    """The `<table>.tabledoc.yml` files. ``models`` maps each dbt model's SQL file to its table.

    Other YAML is not read; YAML with tabledoc's table schema under another name is an error."""
    models = models or {}
    tables = []
    for path in walk(root, (".yml", ".yaml")):
        if path.parent == root and path.name in (DATASET_FILE, legacy.DATASET_FILE):
            continue
        try:
            record = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        schema = record.get("$schema") if isinstance(record, dict) else None
        if isinstance(schema, str) and schema.startswith(schemas.MOVED_BASE):
            raise _unknown(schema, path)
        if not isinstance(schema, str) or not schema.startswith(schemas.BASE):
            continue
        if schema != schemas.TABLE:
            raise _unknown(schema, path)
        if not path.name.endswith(TABLE_SUFFIX):
            report.error("table-misnamed", f"a table file is named <table>{TABLE_SUFFIX}", path)
            continue
        schemas.check(record, schemas.TABLE, path, report)
        if record.get("name") not in (None, stem(path)):
            report.error("table-name", f"name {record['name']} is not the file's name {stem(path)}", path)
            continue
        key = _table_key(root, path, models, report)
        if key is not None:
            body = {k: v for k, v in record.items() if k not in ("$schema", "name")}
            tables.append(Table(*key, record=body, path=path, guide=sibling_guide(root, path)))
    return tables


def legacy_front_matter(path: Path) -> tuple[dict[str, Any], str] | None:
    """(front matter, body) of a Markdown table file in the older format, else None."""
    split = legacy.split_front_matter(path.read_text(encoding="utf-8"))
    if split is None:
        return None
    try:
        record = yaml.safe_load(split[0])
    except yaml.YAMLError:
        return None
    schema = record.get("$schema") if isinstance(record, dict) else None
    if not isinstance(schema, str) or not schema.startswith(schemas.LEGACY_BASE):
        return None
    if schema != schemas.LEGACY_TABLE:
        raise _unknown(schema, path)
    return record, split[1].lstrip("\r\n")


def read_legacy_tables(root: Path, report: Report) -> list[Table]:
    """Markdown with a table in its front matter (the older format)."""
    tables = []
    for path in walk(root, (".md",)):
        found = legacy_front_matter(path)
        if found is None:
            continue
        record, body = found
        schemas.check(record, schemas.LEGACY_TABLE, path, report)
        if not isinstance(record.get("table"), str) or "." not in record["table"]:
            continue
        schema, name = record["table"].split(".", 1)
        converted = legacy.table({k: v for k, v in record.items() if k not in ("$schema", "table")})
        tables.append(
            Table(schema, name, record=converted, path=path, guide=rel(root, path) if body.strip() else None)
        )
    if tables:
        report.info("legacy-format", f"{len(tables)} tables read from Markdown front matter; move them to <table>{TABLE_SUFFIX}")
    return tables
