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
    path: str
    sha256: str
    bytes: int
    media_type: str

    def entry(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes, "media_type": self.media_type}


def describe(root: Path, path: str) -> File:
    body = content(root, path)
    return File(path, hashlib.sha256(body).hexdigest(), len(body), media_type(path))


def collect(root: Path, documents: list[tuple[str, Path]], report: Report) -> list[File]:
    """``documents`` (path, the file that names it) and the files their Markdown links to.

    A named document that is missing, or outside the root, is an error. A link
    to a folder is left alone; a link to a missing file is a warning.
    """
    seen: dict[str, File] = {}
    pending = list(documents)
    named = {path for path, _ in documents}
    while pending:
        path, where = pending.pop(0)
        if path in seen:
            continue
        file = root / path
        if not file.is_file() or not file.resolve().is_relative_to(root.resolve()):
            if path in named:
                report.error("file-missing", f"{path} is not a file under {root}", where)
            elif not file.is_dir():
                report.warning("link-broken", f"links to {path}, which is not here", where)
            continue
        seen[path] = describe(root, path)
        if path.lower().endswith(".md"):
            text = content(root, path).decode("utf-8", errors="replace")
            for target in links(text):
                linked = normalized(posixpath.join(posixpath.dirname(path), target))
                if linked is None:
                    report.error("link-outside", f"links to {target}, outside {root}", file)
                elif linked not in seen:
                    pending.append((linked, file))
    return [seen[p] for p in sorted(seen)]
