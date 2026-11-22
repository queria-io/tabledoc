"""tabledoc load: write a description into the `_fdl` schema of fdl's working metadata, and the files `fdl commit` uploads.

The working metadata is the one `fdl clone` made and the build wrote. `fdl meta set --replace --stdin`
writes the description's rows (`fdl.rows`) into its `_fdl` schema, and the folder
``out`` gets the files of `_fdl.files` (for `fdl commit --assets`).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from . import fdl
from .description import MANIFEST_MISSING, Description, Options, read
from .report import Finding, Level, Report, SpecError

#: Marks a folder load wrote, which the next load may replace.
MARK = ".tabledoc-load"


@dataclass(frozen=True)
class Target:
    #: fdl's working metadata (the .sqlite `fdl clone` made).
    working: str
    #: The folder for `fdl commit --assets`; None writes `_fdl` only.
    out: Path | None = None
    #: Files the build made for its asset columns, linked into ``out/data``.
    assets: Path | None = None
    #: Write the tables and views that have no description, as not published.
    unlisted: bool = False


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


def _missing(columns: dict[fdl.Key, dict[str, str]], description: Description, report: Report) -> None:
    """Each described table and column, and each primary key column, has to be in the
    working metadata, and an asset column has to be varchar. fdl checks these too;
    here they are named by the file that says them.

    Names match without regard to case, as DuckDB's identifiers do. A view's columns
    are known only once it is bound, so fdl checks those.
    """
    held = {fdl.fold(*key): {n.lower(): t for n, t in found.items()} for key, found in columns.items()}
    viewed = {fdl.fold(*key) for key, found in columns.items() if not found}
    for table in description.tables:
        key = fdl.fold(table["schema"], table["name"])
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


def _spelled(description: Description, columns: dict[fdl.Key, dict[str, str]]) -> Description:
    """``description`` with its schemas, tables, columns and primary keys named as the
    working metadata spells them, which `_fdl` has to match."""
    names = {fdl.fold(*key): key for key in columns}
    schemas = {key[0].lower(): key[0] for key in columns}

    def table(t: dict[str, Any]) -> dict[str, Any]:
        key = names.get(fdl.fold(t["schema"], t["name"]))
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


def _carried_over(report: Report) -> None:
    """Without dbt's manifest, the catalog's SQL of what dbt built is kept: worth knowing only."""
    report.findings = [
        Finding(Level.INFO, f.code, f"{f.message}; the SQL dbt built last time is kept", f.source)
        if f.code == MANIFEST_MISSING and f.level is Level.WARNING
        else f
        for f in report.findings
    ]


def load(options: Options, target: Target, report: Report, *, strict: bool = False) -> Description | None:
    """Read and check the description, then write it with `fdl meta set --replace --stdin`.

    Nothing is written when the check fails: on an error, or with ``strict`` on a warning.
    """
    description = read(options, report)
    if report.failed or (strict and _warned(report, but=MANIFEST_MISSING)):
        return None
    if target.out is not None:
        check_out(target.out)
    tables, views, columns = fdl.objects(target.working)
    _missing(columns, description, report)
    if report.failed:
        return None
    description = _spelled(description, columns)
    # Without a dbt build, the SQL and dependencies stay as `_fdl` has them.
    carried = fdl.dump(target.working)
    if fdl.built_by_dbt(carried):
        _carried_over(report)
    if strict and _warned(report):
        return None
    unlisted = tables | views if target.unlisted else None
    refused = fdl.load(target.working, fdl.rows(description, carried, unlisted, views))
    if refused:
        report.error("fdl", refused, description.root)
        return None
    if target.out is not None:
        write_out(description, target.out, target.assets)
    return description
