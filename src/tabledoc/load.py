"""tabledoc load: write a description into a DuckLake catalog, and what `fdl commit` takes.

The catalog is the one the build wrote (with fdl, the working catalog `fdl clone`
made). Its `_meta` schema gets the description (`meta.rows`), and the folder
``out`` gets ``dataset.json`` (the primary keys and asset columns, for
`fdl commit --dataset`) and ``assets/`` (the guides and documents, for
`fdl commit --assets`).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import meta
from .description import Description, Options, read
from .report import Level, Report, SpecError

ALIAS = "lake"
#: Marks a folder load wrote, which the next load may replace.
MARK = ".tabledoc-load"
ASSETS = "assets"


@dataclass(frozen=True)
class Target:
    #: The DuckLake catalog: a .sqlite or .duckdb file, or a ducklake: path.
    catalog: str
    #: Where new data files go; default the note `fdl clone` wrote beside the catalog.
    data_path: str | None = None
    #: The folder for fdl commit; None writes the catalog only.
    out: Path | None = None
    #: Files the build made for its asset columns, linked into ``out/assets/data``.
    assets: Path | None = None
    #: Write the catalog's tables that have no description, as not published.
    unlisted: bool = False


def data_path(catalog: str, given: str | None) -> str | None:
    """``given``, else the local folder `fdl clone` noted in ``<catalog>.fdl.json``."""
    if given:
        return given
    note = Path(catalog + ".fdl.json")
    if not note.is_file():
        return None
    try:
        data = json.loads(note.read_text(encoding="utf-8")).get("data")
    except (OSError, ValueError, AttributeError) as exc:
        raise SpecError(f"cannot read {note}: {exc}") from exc
    return Path(data).resolve().as_posix() + "/" if data else None


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
        options += [f"DATA_PATH '{data}'", "OVERRIDE_DATA_PATH true"]
    con = duckdb.connect()
    try:
        con.execute("INSTALL ducklake; LOAD ducklake; INSTALL httpfs; LOAD httpfs;")
        if catalog.endswith(".sqlite"):
            con.execute("INSTALL sqlite; LOAD sqlite;")
        try:
            con.execute(f"ATTACH '{target}' AS {ALIAS} ({', '.join(options)})")
        except duckdb.Error as exc:
            raise SpecError(f"cannot open {catalog}: {exc}") from exc
        yield con
    finally:
        con.close()


def check_out(out: Path) -> None:
    """Raise SpecError unless ``out`` is missing, empty, or what load wrote before."""
    if out.exists() and not out.is_dir():
        raise SpecError(f"{out} is a file; give a folder")
    if out.is_dir() and any(out.iterdir()) and not (out / MARK).is_file():
        raise SpecError(f"{out} holds files tabledoc did not write; give an empty folder")


def write_out(description: Description, out: Path, assets: Path | None) -> None:
    check_out(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # Hidden, so fdl commit leaves it out of the version.
    (out / MARK).write_text("written by tabledoc load; the next load replaces this folder\n", encoding="utf-8")
    structure = json.dumps(meta.structure(description), ensure_ascii=False, indent=2)
    (out / "dataset.json").write_text(structure + "\n", encoding="utf-8")
    (out / ASSETS).mkdir()
    meta.write_assets(description, out / ASSETS, assets)


def _missing(con: Any, description: Description, report: Report) -> None:
    """Each described table and column, and each primary key column, has to be in the catalog."""
    present = meta.relations(con, ALIAS)
    found = con.execute(
        "SELECT schema_name, table_name, column_name FROM duckdb_columns() WHERE database_name = ?", [ALIAS]
    ).fetchall()
    columns = {(s, t): set() for s, t in present}
    for schema, table, name in found:
        columns.setdefault((schema, table), set()).add(name)
    for table in description.tables:
        key = (table["schema"], table["name"])
        if key not in present:
            report.error("table-missing", f"{'.'.join(key)} is described but is not in the catalog", description.root)
            continue
        named = [c.get("name") for c in table.get("columns") or []] + list(table.get("primary_key") or [])
        for name in dict.fromkeys(named):
            if name not in columns[key]:
                report.error(
                    "column-missing",
                    f"{'.'.join(key)}.{name} is described but is not in the catalog",
                    description.root,
                )


def load(options: Options, target: Target, report: Report, *, strict: bool = False) -> Description | None:
    """Read and check the description, then write it.

    Nothing is written when the check fails: on an error, or with ``strict`` on a warning.
    """
    description = read(options, report)
    if report.failed or (strict and report.of(Level.WARNING)):
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
            carried = meta.read(con, ALIAS) if not any("sql" in t for t in description.tables) else None
            unlisted = meta.relations(con, ALIAS) if target.unlisted else None
            meta.write(con, ALIAS, meta.rows(description, carried, unlisted))
    except duckdb.Error as exc:
        raise SpecError(f"cannot write {meta.SCHEMA} in {target.catalog}: {exc}") from exc
    if target.out is not None:
        write_out(description, target.out, target.assets)
    return description

