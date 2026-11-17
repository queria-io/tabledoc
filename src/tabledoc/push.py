"""`tabledoc push`: send tabledoc.json, and the files it lists that the receiver lacks.

    PUT <url>                       tabledoc.json (gzip)
      <- 409 {"missing": [sha256, ...]}
    PUT <url without query>/files/<sha256>   each missing file
    PUT <url>                       again: 201 a new revision, 200 the same content
"""

from __future__ import annotations

import gzip
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import files

USER_AGENT = "tabledoc"


class PushError(Exception):
    pass


@dataclass(frozen=True)
class Reply:
    status: int
    body: dict[str, Any]


def _put(url: str, body: bytes, headers: dict[str, str]) -> Reply:
    request = urllib.request.Request(url, data=body, method="PUT", headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return Reply(response.status, _json(response.read()))
    except urllib.error.HTTPError as error:
        return Reply(error.code, _json(error.read()))


def _json(raw: bytes) -> dict[str, Any]:
    try:
        loaded = json.loads(raw or b"{}")
    except ValueError:
        return {"error": raw.decode("utf-8", errors="replace")[:500]}
    return loaded if isinstance(loaded, dict) else {"body": loaded}


def files_url(url: str, sha256: str) -> str:
    """Where a file goes: the push URL without its query, then /files/<sha256>."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(path=parts.path.rstrip("/") + f"/files/{sha256}", query=""))


def _contents(root: Path, document: dict[str, Any]) -> dict[str, tuple[bytes, str]]:
    """sha256 -> (content, media type) of each file tabledoc.json lists, as they are now."""
    found = {}
    for entry in document.get("files") or []:
        body = files.content(root, entry["path"])
        if hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise PushError(f"{entry['path']} changed since tabledoc.json was built; run tabledoc build again")
        found[entry["sha256"]] = (body, entry["media_type"])
    return found


def push(
    url: str,
    document: dict[str, Any],
    root: Path,
    token: str,
    put: Callable[[str, bytes, dict[str, str]], Reply] = _put,
    log: Callable[[str], None] = print,
) -> Reply:
    contents = _contents(root, document)
    auth = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    body = gzip.compress(json.dumps(document, ensure_ascii=False).encode("utf-8"), mtime=0)
    headers = {**auth, "Content-Type": "application/json", "Content-Encoding": "gzip"}
    reply = put(url, body, headers)
    if reply.status == 409 and isinstance(reply.body.get("missing"), list):
        for sha256 in reply.body["missing"]:
            if sha256 not in contents:
                raise PushError(f"the receiver asks for {sha256}, which tabledoc.json does not list")
            content, media_type = contents[sha256]
            sent = put(files_url(url, sha256), content, {**auth, "Content-Type": media_type})
            if sent.status not in (200, 201):
                raise PushError(f"sending {sha256}: {sent.status} {sent.body}")
            log(f"sent {sha256}")
        reply = put(url, body, headers)
    if reply.status not in (200, 201):
        raise PushError(f"{reply.status} {reply.body}")
    return reply
