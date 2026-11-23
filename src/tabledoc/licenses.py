"""The licenses tabledoc knows by id: SPDX identifiers and the terms of use that have none.

A license written by such an id is filled in from `licenses.json`, so every catalog holds
the same title, URL and terms for it and a description cannot restate them differently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: id -> {id, url, title, commercial_use, share_alike, attribution_required}; the title is
#: {tag: text}, in the language the license is published in.
KNOWN: dict[str, dict[str, Any]] = {
    id_: {"id": id_, **entry}
    for id_, entry in json.loads((Path(__file__).parent / "licenses.json").read_text(encoding="utf-8")).items()
}


def known(entry: dict[str, Any], language: str) -> dict[str, Any] | None:
    """The known license ``entry`` names by its id, or None. Its url is held as text in
    ``language``, as a Description holds the text of an entry."""
    held = KNOWN.get(entry.get("id"))
    return {**held, "url": {language: held["url"]}} if held else None


def held_as(id_: str) -> dict[str, Any] | None:
    """The known license ``id_`` as the tables hold it: each text as the text alone."""
    held = KNOWN.get(id_)
    return {**held, "title": next(iter(held["title"].values()))} if held else None
