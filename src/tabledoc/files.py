"""The files whose content is sent: guides, README.md, docs, and what they link to.

Each is named by its path under the root, with its sha256. A
Markdown table file of the older format is sent without its front matter.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .report import Report
from .source import legacy_front_matter

#: Relative links in Markdown: [text](target), ![alt](target), and src="target".
_LINK = re.compile(r"""(\]\(\s*<?)([^)\s>]+)|(\bsrc\s*=\s*["'])([^"']+)""")

#: Fixed, so the same file gets the same type on every machine.
MEDIA_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
    ".geojson": "application/geo+json",
    ".yml": "application/yaml",
    ".yaml": "application/yaml",
    ".xml": "application/xml",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".avif": "image/avif",
}
OCTET_STREAM = "application/octet-stream"


def media_type(path: str) -> str:
    return MEDIA_TYPES.get(posixpath.splitext(path)[1].lower(), OCTET_STREAM)


def content(root: Path, path: str) -> bytes:
    """What is sent for ``path``: the file, or a Markdown table file's text below its front matter."""
    file = root / path
    if path.lower().endswith(".md"):
        found = legacy_front_matter(file)
        if found is not None:
            return found[1].encode("utf-8")
    return file.read_bytes()


def _is_relative(target: str) -> bool:
    return not (target.startswith(("#", "/")) or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE))


def links(text: str) -> list[str]:
    """The relative link targets in ``text``, without #fragment or ?query."""
    found = (m.group(2) or m.group(4) for m in _LINK.finditer(text))
    return [t for t in (re.split(r"[?#]", f)[0] for f in found if _is_relative(f)) if t]


def normalized(path: str) -> str | None:
    """``path`` normalized, or None when it leaves the root."""
    clean = posixpath.normpath(path)
    return None if clean == ".." or clean.startswith("../") or posixpath.isabs(clean) else clean


@dataclass(frozen=True)
class File:
    #: Its path in the dataset (the version), with `/` between folders.
    path: str
    sha256: str
    bytes: int
    media_type: str
    #: Its path under the root, where the author keeps it.
    local: str = ""

    def entry(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes, "media_type": self.media_type}


def _relink(text: str, local: str, path: str, placed: dict[str, str]) -> str:
    """``text`` of the Markdown at ``local``, placed at ``path``: each relative link to a file
    placed elsewhere points at its new place, from ``path``'s folder. Other links stay as written."""

    def swap(target: str) -> str:
        bare = re.split(r"[?#]", target)[0]
        if not bare or not _is_relative(target):
            return target
        found = normalized(posixpath.join(posixpath.dirname(local), bare))
        new = placed.get(found or "")
        if new is None or normalized(posixpath.join(posixpath.dirname(path), bare)) == new:
            return target
        return posixpath.relpath(new, posixpath.dirname(path) or ".") + target[len(bare) :]

    def replace(m: re.Match[str]) -> str:
        if m.group(2) is not None:
            return m.group(1) + swap(m.group(2))
        return m.group(3) + swap(m.group(4))

    return _LINK.sub(replace, text)


def body(root: Path, file: File, placed: dict[str, str]) -> bytes:
    """What goes into the dataset for ``file``: a Markdown document with its links following
    the files that moved (``placed``: path under the root -> path in the dataset), else the file."""
    raw = content(root, file.local)
    if not file.local.lower().endswith(".md") or all(k == v for k, v in placed.items()):
        return raw
    text = raw.decode("utf-8", errors="surrogateescape")
    return _relink(text, file.local, file.path, placed).encode("utf-8", errors="surrogateescape")


def collect(root: Path, documents: list[tuple[str, str, Path]], report: Report) -> list[File]:
    """``documents`` (path under the root, path in the dataset, the file that names it) and
    the files their Markdown links to, each at its path in the dataset.

    A file linked to and not named keeps its path under the root. A Markdown
    document's links are rewritten to follow the files that moved. A named
    document that is missing, or outside the root, is an error. A link to a
    folder is left alone; a link to a missing file is a warning. Two files at
    the same path in the dataset is an error, and so is one file named for two
    paths in the dataset.
    """
    placed: dict[str, str] = {}
    pending = [(local, where) for local, _, where in documents]
    named: dict[str, str] = {}
    for local, path, where in documents:
        if named.setdefault(local, path) != path:
            report.error("file-named-twice", f"{local} is named for both {named[local]} and {path} in the dataset", where)
    while pending:
        local, where = pending.pop(0)
        if local in placed:
            continue
        file = root / local
        if not file.is_file() or not file.resolve().is_relative_to(root.resolve()):
            if local in named:
                report.error("file-missing", f"{local} is not a file under {root}", where)
            elif not file.is_dir():
                report.warning("link-broken", f"links to {local}, which is not here", where)
            continue
        placed[local] = named.get(local, local)
        if local.lower().endswith(".md"):
            text = content(root, local).decode("utf-8", errors="replace")
            for target in links(text):
                linked = normalized(posixpath.join(posixpath.dirname(local), target))
                if linked is None:
                    report.error("link-outside", f"links to {target}, outside {root}", file)
                elif linked not in placed:
                    pending.append((linked, file))
    taken: dict[str, str] = {}
    for local, path in sorted(placed.items()):
        if path in taken:
            report.error("file-clash", f"{local} and {taken[path]} both go to {path} in the dataset", root / local)
        taken[path] = local
    found = []
    for local, path in placed.items():
        sent = body(root, File(path, "", 0, "", local), placed)
        found.append(File(path, hashlib.sha256(sent).hexdigest(), len(sent), media_type(path), local))
    return sorted(found, key=lambda f: f.path)
