"""What `fdl status --json` says of fdl's working metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .report import SpecError

#: Runs fdl with these arguments and gives what it printed.
Run = Callable[[list[str]], str]


def call(args: list[str]) -> str:
    """Run fdl on PATH with ``args`` and give what it printed."""
    fdl = shutil.which("fdl")
    if fdl is None:
        raise SpecError("the catalog is fdl's working metadata, but fdl is not on PATH")
    done = subprocess.run([fdl, *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SpecError(f"fdl {' '.join(args)} failed: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout


def working(catalog: str) -> Path | None:
    """The working metadata ``catalog`` is, when `fdl clone` made it (the folder
    ``<catalog>.fdl`` is beside it); else None."""
    path = Path(catalog.removeprefix("ducklake:"))
    return path if path.with_name(path.name + ".fdl").is_dir() else None


def status(catalog: str, run: Run | None = None) -> dict[str, Any] | None:
    """`fdl status --json` of ``catalog``, when `fdl clone` made it; else None.

    It gives ``remote``, ``base`` and ``data_path`` (fdl-cli 0.35 or later).
    """
    path = working(catalog)
    if path is None:
        return None
    try:
        found = json.loads((run or call)(["status", str(path), "--json"]))
    except ValueError as exc:
        raise SpecError(f"fdl status printed what is not JSON: {exc}") from exc
    if not isinstance(found, dict) or "data_path" not in found:
        raise SpecError("fdl status --json gives no remote or data_path: tabledoc needs fdl-cli 0.35 or later")
    return found
