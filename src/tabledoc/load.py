"""tabledoc load: write a description into a DuckLake catalog, and the files `fdl commit` uploads.

The catalog is the one the build wrote (with fdl, the working metadata `fdl clone`
made). The description's rows (`tables.rows`) go into the tables of a schema
of it (`_tabledoc` unless told otherwise), and the folder ``out`` gets the files
of its `files` table (for `fdl commit --assets`). With fdl's working metadata, the
primary keys, asset columns and dependencies are declared with `fdl declare`.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from . import fdl_state, tables
from .declare import declare
from .description import MANIFEST_MISSING, Description, Options, read
from .report import Finding, Level, Report, SpecError

#: Marks a folder load wrote, which the next load may replace.
MARK = ".tabledoc-load"
ALIAS = "lake"


@dataclass(frozen=True)
class Target:
    #: The DuckLake catalog: a .sqlite or .duckdb file, or a ducklake: path.
    catalog: str
    #: Where new data files go; default where `fdl status` says, for fdl's working metadata.
    data_path: str | None = None
    #: The folder for `fdl commit --assets`; None writes the catalog only.
    out: Path | None = None
    #: Files the build made for its asset columns, linked into ``out/data``.
    assets: Path | None = None
    #: Write the catalog's tables that have no description, with `hidden` true.
    hide_undescribed: bool = False
    #: The schema to write into; default `_tabledoc`.
    schema: str | None = None


def data_path(catalog: str, given: str | None) -> str | None:
    """``given``, else where new data files go as `fdl status` says, when `fdl clone`
    made the catalog; else None (the catalog's own data path)."""
    if given:
        return given
    found = fdl_state.status(catalog)
    return found["data_path"] if found else None


def _string(value: str) -> str:
    """``value`` as an SQL string literal."""
    return "'" + value.replace("'", "''") + "'"


def remote_secret(catalog: str) -> str | None:
    """The DuckDB secret that sends `FDL_TOKEN` to the HTTP remote `fdl clone` made
    ``catalog`` from, so the data files of a private dataset can be read; None without both."""
    token = os.environ.get("FDL_TOKEN")
    found = fdl_state.status(catalog) if token else None
    remote = found.get("remote") if found else None
    if not isinstance(remote, str) or not remote.startswith(("http://", "https://")):
        return None
    return f"CREATE SECRET tabledoc_remote (TYPE http, BEARER_TOKEN {_string(token)}, SCOPE {_string(remote)})"


@contextmanager
def attached(catalog: str, data: str | None, *, read_only: bool = False) -> Iterator[Any]:
    """A DuckDB connection with ``catalog`` attached as ``ALIAS``: writable, unless ``read_only``.

    Every row goes to a data file (`DATA_INLINING_ROW_LIMIT 0`), as fdl commit
    requires. Files over HTTP are read with httpfs and DuckDB's own secrets; with
    fdl's working metadata, `FDL_TOKEN` is sent to its remote (`remote_secret`).
    """
    import duckdb

    target = catalog if catalog.startswith("ducklake:") else f"ducklake:{catalog}"
    options = ["READ_ONLY"] if read_only else ["DATA_INLINING_ROW_LIMIT 0"]
    if catalog.endswith(".sqlite"):
        options.append("META_TYPE 'sqlite'")
    if data:
        options += [f"DATA_PATH {_string(data)}", "OVERRIDE_DATA_PATH true"]
    con = duckdb.connect()
    try:
        con.execute("INSTALL ducklake; LOAD ducklake; INSTALL httpfs; LOAD httpfs;")
        if catalog.endswith(".sqlite"):
            con.execute("INSTALL sqlite; LOAD sqlite;")
        secret = remote_secret(catalog)
        if secret:
            con.execute(secret)
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

    Each file of the files table under ``out/files/<path>``, its extension kept so
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


def _missing(columns: dict[tables.Key, dict[str, str]], description: Description, report: Report) -> None:
    """Each described table and column, and each primary key column, has to be in the
    catalog, and an asset column has to be varchar.

    Names match without regard to case, as DuckDB's identifiers do.
    """
    held = {tables.fold(*key): {n.lower(): t for n, t in found.items()} for key, found in columns.items()}
    viewed = {tables.fold(*key) for key, found in columns.items() if not found}
    for table in description.tables:
        key = tables.fold(table["schema"], table["name"])
        where = f"{table['schema']}.{table['name']}"
        if key not in held:
            report.error("table-missing", f"{where} is described but is not in the catalog", description.root)
            continue
        if key in viewed:
            continue
        named = [c.get("name") for c in table.get("columns") or []] + list(table.get("primary_key") or [])
        for name in dict.fromkeys(named):
            if not isinstance(name, str) or name.lower() not in held[key]:
                report.error("column-missing", f"{where}.{name} is described but is not in the catalog", description.root)
        for column in table.get("columns") or []:
            name = column.get("name")
            if column.get("asset") is True and isinstance(name, str) and held[key].get(name.lower(), "VARCHAR") != "VARCHAR":
                report.error("asset-type", f"{where}.{name} holds assets, so it has to be varchar", description.root)


def _spelled(description: Description, columns: dict[tables.Key, dict[str, str]]) -> Description:
    """``description`` with its schemas, tables, columns and primary keys named as the
    catalog spells them."""
    names = {tables.fold(*key): key for key in columns}
    schemas = {key[0].lower(): key[0] for key in columns}

    def table(t: dict[str, Any]) -> dict[str, Any]:
        key = names.get(tables.fold(t["schema"], t["name"]))
        if key is None:
            return t
        held = {n.lower(): n for n in columns[key]}

        def spell(name: Any) -> Any:
            return held.get(name.lower(), name) if isinstance(name, str) else name

        return {
            **t,
            "schema": key[0],
            "name": key[1],
            **({"primary_key": [spell(c) for c in t["primary_key"]]} if t.get("primary_key") else {}),
            **({"columns": [{**c, "name": spell(c.get("name"))} for c in t["columns"]]} if t.get("columns") else {}),
        }

    return replace(
        description,
        schemas=[{**s, "name": schemas.get(str(s.get("name")).lower(), s.get("name"))} for s in description.schemas],
        tables=[table(t) for t in description.tables],
    )


def _warned(report: Report, but: str = "") -> bool:
    return any(f.code != but for f in report.of(Level.WARNING))


def _keeps_dbt_sql(description: Description, carried: tables.Rows, undescribed: set[tables.Key] | None) -> bool:
    """Whether the load keeps the SQL of every table dbt built, as the catalog holds it: there
    is such a table, the description has no `sql` (no build), and each of them keeps its row
    (it is described, or ``undescribed`` holds it)."""
    built = {
        tables.fold(t["schema_name"], t["table_name"])
        for t in carried.get("tables") or []
        if t.get("source_path") and t.get("schema_name") is not None
    }
    kept = {tables.fold(t["schema"], t["name"]) for t in description.tables}
    kept |= {tables.fold(*key) for key in undescribed or set()}
    return bool(built) and built <= kept and not any("sql" in t for t in description.tables)


def _carried_over(report: Report) -> None:
    """Without dbt's manifest, the catalog's SQL of what dbt built is kept: worth knowing only."""
    report.findings = [
        Finding(Level.INFO, f.code, f"{f.message}; the SQL dbt built last time is kept", f.source)
        if f.code == MANIFEST_MISSING and f.level is Level.WARNING
        else f
        for f in report.findings
    ]


def schema_of(target: Target, description: Description) -> str:
    """``target.schema``, else `_tabledoc`."""
    return target.schema or tables.SCHEMA


def load(options: Options, target: Target, report: Report, *, strict: bool = False) -> Description | None:
    """Read and check the description, then write it into the catalog.

    Nothing is written when the check fails: on an error, or with ``strict`` on a warning.
    """
    description = read(options, report)
    if not report.failed:
        for where, column, kind in tables.unfit(tables.rows(description)):
            report.error("value-type", f"{where}: {column} cannot be written as {kind}", description.root)
    if not report.failed:
        for where in tables.several(description):
            report.warning(
                "one-language",
                f"{where} is written in more than one language; only the one in `language` is written",
                description.root,
            )
    if report.failed or (strict and _warned(report, but=MANIFEST_MISSING)):
        return None
    if target.out is not None:
        check_out(target.out)
    schema = schema_of(target, description)
    import duckdb

    try:
        with attached(target.catalog, data_path(target.catalog, target.data_path)) as con:
            schema = tables.spelled_schema(con, ALIAS, schema)
            in_catalog, views, columns = tables.relations(con, ALIAS, schema)
            _missing(columns, description, report)
            if report.failed:
                return None
            description = _spelled(description, columns)
            # Without a dbt build, the SQL and dependencies stay as the catalog has them.
            carried = tables.read(con, ALIAS, schema)
            undescribed = in_catalog | views if target.hide_undescribed else None
            if _keeps_dbt_sql(description, carried, undescribed):
                _carried_over(report)
            if strict and _warned(report):
                return None
            found = tables.rows(description, carried, undescribed, views)
            for wrong in tables.dangling(found, schema):
                report.error("dangling-row", wrong, description.root)
            if report.failed:
                return None
            tables.write(con, ALIAS, found, schema)
    except duckdb.Error as exc:
        raise SpecError(f"cannot write {schema} in {target.catalog}: {exc}") from exc
    declare(
        target.catalog,
        description,
        schema,
        hidden={f"{t['schema_name']}.{t['table_name']}" for t in found["tables"] if tables.hidden(t)},
        views={f"{s}.{n}" for s, n in views},
    )
    if target.out is not None:
        write_out(description, target.out, target.assets)
    return description
