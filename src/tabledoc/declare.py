"""Declare to FDL what it reads of the tables: primary keys, asset columns and dependencies.

When the catalog is FDL's working metadata (`fdl clone` noted ``<catalog>.fdl.json``
beside it), `tabledoc load` runs `fdl declare` for what the description says:

- each described table's `primary_key`
- each described table's asset columns, when its columns say `asset`
- the other datasets the SQL reads (dbt's profiles.yml), as dependencies
- the description's own tables: their primary keys, and `files.sha256` as an asset column

Only what differs from `fdl declare list` is run. What the description does not
say is left as FDL has it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import tables
from .description import Description
from .report import SpecError

#: Runs fdl with these arguments and gives what it printed.
Run = Callable[[list[str]], str]


def working(catalog: str) -> Path | None:
    """The working metadata ``catalog`` is, when `fdl clone` made it; else None."""
    path = Path(catalog.removeprefix("ducklake:"))
    return path if Path(f"{path}.fdl.json").is_file() else None


def wanted(description: Description, schema: str) -> dict[str, Any]:
    """What the description declares, in the shape of `fdl declare list --json`."""
    primary_keys: dict[str, list[str]] = {}
    assets: dict[str, list[str]] = {}
    for table in description.tables:
        name = f"{table['schema']}.{table['name']}"
        if table.get("primary_key"):
            primary_keys[name] = list(table["primary_key"])
        columns = table.get("columns") or []
        if any("asset" in c for c in columns):
            assets[name] = [c["name"] for c in columns if c.get("asset") is True]
    for own, (_, key) in tables.TABLES.items():
        primary_keys[f"{schema}.{own}"] = list(key)
    assets.update({f"{schema}.{own}": list(cols) for own, cols in tables.ASSETS.items()})
    dependencies = {alias: {"url": url} for alias, url in sorted((description.catalogs or {}).items())}
    return {"primary_keys": primary_keys, "assets": assets, "dependencies": dependencies}


def commands(have: dict[str, Any], want: dict[str, Any]) -> list[list[str]]:
    """The `fdl declare` arguments (after the working metadata) that make ``have`` say ``want``."""
    out: list[list[str]] = []
    for kind, verb in (("primary_keys", "primary-key"), ("assets", "assets")):
        held = have.get(kind) or {}
        out += [[verb, name, *cols] for name, cols in want[kind].items() if (held.get(name) or []) != cols]
    held = have.get("dependencies") or {}
    out += [
        ["dependency", alias, entry["url"]]
        for alias, entry in want["dependencies"].items()
        if (held.get(alias) or {}).get("url") != entry["url"]
    ]
    return out


def _run(args: list[str]) -> str:
    fdl = shutil.which("fdl")
    if fdl is None:
        raise SpecError("the catalog is fdl's working metadata, but fdl is not on PATH to declare its keys")
    done = subprocess.run([fdl, *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SpecError(f"fdl {' '.join(args)} failed: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout


def declare(catalog: str, description: Description, schema: str, run: Run = _run) -> list[list[str]]:
    """Run `fdl declare` for what differs, when ``catalog`` is fdl's working metadata.

    Gives the commands run (each without `fdl declare <working>`).
    """
    path = working(catalog)
    if path is None:
        return []
    have = json.loads(run(["declare", "list", str(path), "--json"]))
    todo = commands(have, wanted(description, schema))
    for args in todo:
        run(["declare", args[0], str(path), *args[1:]])
    return todo
