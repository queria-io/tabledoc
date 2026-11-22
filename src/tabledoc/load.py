"""tabledoc load: write a description into a DuckLake catalog, and the files `fdl commit` uploads.

The catalog is the one the build wrote (with fdl, the working catalog `fdl clone`
made). Its `_fdl` schema gets the description (`fdl.rows`), and the folder
``out`` gets the files of `_fdl.files` (for `fdl commit --assets`).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from . import fdl
from .description import MANIFEST_MISSING, Description, Options, read
from .report import Finding, Level, Report, SpecError

ALIAS = "lake"
#: Marks a folder load wrote, which the next load may replace.
MARK = ".tabledoc-load"


@dataclass(frozen=True)
class Target:
    #: The DuckLake catalog: a .sqlite or .duckdb file, or a ducklake: path.
    catalog: str
    #: Where new data files go; default the note `fdl clone` wrote beside the catalog.
    data_path: str | None = None
    #: The folder for `fdl commit --assets`; None writes the catalog only.
    out: Path | None = None
    #: Files the build made for its asset columns, linked into ``out/data``.
    assets: Path | None = None
    #: Write the catalog's tables that have no description, as not published.
    unlisted: bool = False


def data_path(catalog: str, given: str | None) -> str | None:
    """``given``, else where `fdl clone` noted in ``<catalog>.fdl.json`` that new data files go.

    As fdl reads the note: the storage's data folder (``--storage``), else the
    local folder (``--data``), else None (the catalog's own data path).
    """
    if given:
        return given
    note = Path(catalog.removeprefix("ducklake:") + ".fdl.json")
    if not note.is_file():
        return None
    try:
        state = json.loads(note.read_text(encoding="utf-8"))
        storage, data, data_dir = state.get("storage"), state.get("data"), state.get("data_dir")
    except (OSError, ValueError, AttributeError) as exc:
        raise SpecError(f"cannot read {note}: {exc}") from exc
    if storage:
        if not data_dir:
            raise SpecError(f"{note} names a storage but no data_dir; give --data-path")
        base = storage if "://" in storage else Path(storage).resolve().as_posix()
        return base.rstrip("/") + "/" + data_dir
    return Path(data).resolve().as_posix() + "/" if data else None


def _string(value: str) -> str:
    """``value`` as an SQL string literal."""
    return "'" + value.replace("'", "''") + "'"


@contextmanager
def attached(catalog: str, data: str | None) -> Iterator[Any]:
    """A DuckDB connection with ``catalog`` attached, writable, as ``ALIAS``.

    Every row goes to a data file (`DATA_INLINING_ROW_LIMIT 0`), as fdl commit
    requires. Files over HTTP are read with httpfs and DuckDB's own secrets.
    """
    import duckdb

    target = catalog if catalog.startswith("ducklake:") else f"ducklake:{catalog}"
    options = ["DATA_INLINING_ROW_LIMIT 0"]
    if catalog.endswith(".sqlite"):
        options.append("META_TYPE 'sqlite'")
    if data:
        options += [f"DATA_PATH {_string(data)}", "OVERRIDE_DATA_PATH true"]
    con = duckdb.connect()
    try:
        con.execute("INSTALL ducklake; LOAD ducklake; INSTALL httpfs; LOAD httpfs;")
        if catalog.endswith(".sqlite"):
            con.execute("INSTALL sqlite; LOAD sqlite;")
        try:
            con.execute(f"ATTACH {_string(target)} AS {ALIAS} ({', '.join(options)})")
        except duckdb.Error as exc:
            raise SpecError(f"cannot open {catalog}: {exc}") from exc
        yield con
    finally:
        con.close()


def check_out(out: Path) -> None:
    """Raise SpecError unless ``out`` is missing, empty, or what load wrote before, outside `.fdl/`."""
    if ".fdl" in out.resolve().parts:
        raise SpecError(f"{out} is inside .fdl/, which only fdl writes; give a folder outside it")
    if out.exists() and not out.is_dir():
        raise SpecError(f"{out} is a file; give a folder")
    if out.is_dir() and any(out.iterdir()) and not (out / MARK).is_file():
        raise SpecError(f"{out} holds files tabledoc did not write; give an empty folder")


def write_out(description: Description, out: Path, assets: Path | None) -> None:
    try:
        _write_out(description, out, assets)
    except OSError as exc:
        raise SpecError(f"cannot write {out}: {exc}") from exc


def _write_out(description: Description, out: Path, assets: Path | None) -> None:
    check_out(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # Hidden, so fdl commit leaves it out.
    (out / MARK).write_text("written by tabledoc load; the next load replaces this folder\n", encoding="utf-8")
    write_files(description, out, assets)


def write_files(description: Description, out: Path, linked: Path | None) -> None:
    """The files `fdl commit --assets out` uploads, found by their content.

    Each file of `_fdl.files` under ``out/files/<path>``, its extension kept so
    the upload carries its media type. fdl leaves hidden files and folders out,
    so a file with a hidden part in its path goes to ``out/files/<sha256><suffix>``.
    With ``linked`` (the build's own assets), every file below it is linked
    under ``out/data/`` so one folder holds both.
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


def _missing(con: Any, description: Description, report: Report) -> None:
    """The checks of the _fdl schema: each described table and column, and each primary
    key column, has to be in the catalog, and an asset column has to be varchar.

    Names match without regard to case, as DuckDB's identifiers do.
    """
    tables, views = fdl.relations(con, ALIAS)
    present = {fdl.fold(s, t) for s, t in tables | views}
    found = con.execute(
        "SELECT schema_name, table_name, column_name, data_type FROM duckdb_columns() WHERE database_name = ?",
        [ALIAS],
    ).fetchall()
    columns: dict[tuple[str, ...], dict[str, str]] = {key: {} for key in present}
    for schema, table, name, kind in found:
        columns.setdefault(fdl.fold(schema, table), {})[name.lower()] = kind
    for table in description.tables:
        key = (table["schema"], table["name"])
        where = ".".join(key)
        if fdl.fold(*key) not in present:
            report.error("table-missing", f"{where} is described but is not in the catalog", description.root)
            continue
        held = columns[fdl.fold(*key)]
        named = [c.get("name") for c in table.get("columns") or []] + list(table.get("primary_key") or [])
        for name in dict.fromkeys(named):
            if not isinstance(name, str) or name.lower() not in held:
                report.error("column-missing", f"{where}.{name} is described but is not in the catalog", description.root)
        for column in table.get("columns") or []:
            name = column.get("name")
            if column.get("asset") is True and isinstance(name, str) and held.get(name.lower(), "VARCHAR") != "VARCHAR":
                report.error("asset-type", f"{where}.{name} holds assets, so it has to be varchar", description.root)


def _warned(report: Report, but: str = "") -> bool:
    return any(f.code != but for f in report.of(Level.WARNING))


def _carried_over(report: Report) -> None:
    """Without dbt's manifest, the catalog's SQL of what dbt built is kept: worth knowing only."""
    report.findings = [
        Finding(Level.INFO, f.code, f"{f.message}; the SQL dbt built last time is kept", f.source)
        if f.code == MANIFEST_MISSING and f.level is Level.WARNING
        else f
        for f in report.findings
    ]


def load(options: Options, target: Target, report: Report, *, strict: bool = False) -> Description | None:
    """Read and check the description, then write it.

    Nothing is written when the check fails: on an error, or with ``strict`` on a warning.
    """
    description = read(options, report)
    if not report.failed:
        for where, column, kind in fdl.unfit(fdl.rows(description)):
            report.error("fdl-type", f"{where}: {column} cannot be written as {kind}", description.root)
    if report.failed or (strict and _warned(report, but=MANIFEST_MISSING)):
        return None
    if target.out is not None:
        check_out(target.out)
    import duckdb

    try:
        with attached(target.catalog, data_path(target.catalog, target.data_path)) as con:
            _missing(con, description, report)
            if report.failed:
                return None
            # Without a dbt build, the SQL and dependencies stay as the catalog has them.
            carried = fdl.read(con, ALIAS) or fdl.read(con, ALIAS, fdl.OLD_SCHEMA)
            if fdl.built_by_dbt(carried):
                _carried_over(report)
            if strict and _warned(report):
                return None
            tables, views = fdl.relations(con, ALIAS)
            unlisted = tables | views if target.unlisted else None
            fdl.write(con, ALIAS, fdl.rows(description, carried, unlisted, views))
    except duckdb.Error as exc:
        raise SpecError(f"cannot write {fdl.SCHEMA} in {target.catalog}: {exc}") from exc
    if target.out is not None:
        write_out(description, target.out, target.assets)
    return description
