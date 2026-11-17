"""Where a description came from: the Git working copy around the root."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def https(url: str) -> str:
    """A remote URL as https, without credentials or `.git`: git@github.com:a/b.git -> https://github.com/a/b."""
    scp = re.fullmatch(r"(?:[^@/]+@)?([^:/]+):(?!//)(.+)", url)
    if scp:
        url = f"https://{scp.group(1)}/{scp.group(2)}"
    url = re.sub(r"^(?:ssh|git|http)://", "https://", url)
    url = re.sub(r"^https://[^@/]+@", "https://", url)
    return url.removesuffix("/").removesuffix(".git")


def source(root: Path) -> dict[str, Any] | None:
    """{repository, commit, path, dirty}, or None outside Git."""
    top = _git(root, "rev-parse", "--show-toplevel")
    commit = _git(root, "rev-parse", "HEAD")
    if top is None or commit is None:
        return None
    remote = _git(root, "remote", "get-url", "origin")
    status = _git(root, "status", "--porcelain")
    path = root.resolve().relative_to(Path(top).resolve()).as_posix()
    return {
        **({"repository": https(remote)} if remote else {}),
        "commit": commit,
        "path": "" if path == "." else path,
        "dirty": bool(status),
    }
