"""The formats before tabledoc, read as tabledoc's.

- queria.yml (https://queria.io/schemas/dataset/v1.json) as tabledoc.yml:
  `title_kana` is `title_reading`, `cover` is `image`
- Markdown whose front matter is https://queria.io/schemas/table/v1.json, as a
  table file (the front matter) and its guide (the text below): `published` is `listed`
"""

from __future__ import annotations

import re
from typing import Any

DATASET_FILE = "queria.yml"
#: Keys queria.yml and the table front matter wrote at the top level, as tabledoc's keys.
#: `themes` and the rest of `ai_context` are not read; `synonyms` is the one part of
#: `ai_context` tabledoc has a key for.
RENAMED = {
    "dataset": {"title_kana": "title_reading", "cover": "image"},
    "table": {"published": "listed"},
}
DROPPED = ("themes", "ai_context")

_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?\r?\n)?---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.DOTALL)


def split_front_matter(text: str) -> tuple[str, str] | None:
    """(front matter, body) of a Markdown file, or None when it has none."""
    match = _FRONT_MATTER.match(text)
    return (match.group(1) or "", match.group(2)) if match else None


def _renamed(record: dict[str, Any], level: str) -> dict[str, Any]:
    """``record`` with the older keys as tabledoc's, and keys tabledoc has no place for left out."""
    renamed = RENAMED[level]
    context = record.get("ai_context")
    synonyms = context.get("synonyms") if isinstance(context, dict) else None
    written = record.get("annotations") if isinstance(record.get("annotations"), dict) else {}
    others = {k: v for k, v in written.items() if k != "queria"}
    rest = {renamed.get(k, k): v for k, v in record.items() if k not in (*DROPPED, "annotations")}
    return {
        **rest,
        **({"synonyms": synonyms} if synonyms and "synonyms" not in rest else {}),
        **({"annotations": others} if others else {}),
    }


def _documents(record: dict[str, Any], guide: bool = False) -> dict[str, Any]:
    """``record`` with `docs` (and a schema's `guide`) as `documents`."""
    listed = [record[k] for k in (("guide",) if guide else ()) if record.get(k)]
    listed += [str(d) for d in record.get("docs") or []] if isinstance(record.get("docs"), list) else []
    rest = {k: v for k, v in record.items() if k not in ("docs", *(("guide",) if guide else ()))}
    return {**rest, **({"documents": listed} if listed else {})}


def dataset(record: dict[str, Any]) -> dict[str, Any]:
    """queria.yml as tabledoc.yml. `catalogs` stays; the caller takes it out as `dependencies`."""
    converted = _documents(_renamed(record, "dataset"))
    written = converted.get("schemas")
    if isinstance(written, list):
        converted["schemas"] = [_documents(s, guide=True) if isinstance(s, dict) else s for s in written]
    return converted


def _semantic(field: dict[str, Any], primary_key: list[str]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """A field's `semantic` as the column's entity or dimension, or as a metric."""
    semantic = field.get("semantic")
    rest = {k: v for k, v in field.items() if k != "semantic"}
    if not isinstance(semantic, dict):
        return rest, None
    role, name = semantic.get("role"), semantic.get("name")
    named = {"name": name} if name else {}
    if role == "entity":
        kind = "primary" if primary_key == [field.get("name")] else "foreign"
        return {**rest, "entity": {"type": kind, **named}}, None
    if role == "dimension":
        return {**rest, "dimension": {"type": "categorical", **named}}, None
    if role == "measure":
        agg = {"agg": semantic["agg"]} if semantic.get("agg") else {}
        return rest, {"name": field.get("name"), **agg, "expr": field.get("name")}
    return rest, None


def table(record: dict[str, Any]) -> dict[str, Any]:
    """A table front matter as a table file. `fields` is `columns`, `semantic` is read as dbt's."""
    own = _documents(_renamed(record, "table"))
    fields = own.pop("fields", None)
    primary_key = own.get("primary_key") if isinstance(own.get("primary_key"), list) else []
    converted = [
        _semantic(f, primary_key) if isinstance(f, dict) else (f, None)
        for f in (fields if isinstance(fields, list) else [])
    ]
    metrics = [m for _, m in converted if m is not None]
    return {
        **own,
        **({"columns": [c for c, _ in converted]} if fields is not None else {}),
        **({"metrics": [*(own.get("metrics") or []), *metrics]} if metrics else {}),
    }
