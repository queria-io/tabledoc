"""The formats before tabledoc, read as tabledoc's.

- queria.yml (https://queria.io/schemas/dataset/v1.json) as tabledoc.yml:
  `title_kana` is `title_reading`, `keywords` is `topics`, and `cover` is `image` when it is a file's path
- Markdown whose front matter is https://queria.io/schemas/table/v1.json, as a
  table file (the front matter) and its guide (the text below): `keywords` is `topics`,
  and `published` is `hidden` negated
- A source's or contributor's `path` is its `url`
"""

from __future__ import annotations

import posixpath
import re
from typing import Any

DATASET_FILE = "queria.yml"
#: Keys queria.yml and the table front matter wrote at the top level, as tabledoc's keys.
#: `themes` and the rest of `ai_context` are not read; `synonyms` is the one part of
#: `ai_context` tabledoc has a key for.
RENAMED = {
    "dataset": {"title_kana": "title_reading", "keywords": "topics", "cover": "image"},
    "table": {"keywords": "topics"},
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
    # A cover was often an emoji, not a file: only a file's path is an image.
    skipped = {*DROPPED, "annotations", *(("cover",) if not _a_path(record.get("cover")) else ())}
    rest = {renamed.get(k, k): v for k, v in record.items() if k not in skipped and k != "published"}
    published = record.get("published")
    hidden = {"hidden": not published} if isinstance(published, bool) else {}
    return {
        **hidden,
        **rest,
        **({"synonyms": synonyms} if synonyms and "synonyms" not in rest else {}),
        **({"annotations": others} if others else {}),
    }


def _a_path(value: Any) -> bool:
    """Whether ``value`` names a file: text with a file extension."""
    return isinstance(value, str) and bool(posixpath.splitext(value.strip())[1])


def _ids(record: dict[str, Any]) -> dict[str, Any]:
    """``record`` with `path` as `url` and an `id` on each source and contributor, which the
    older format did not have: its `path`, else its `title`."""

    def with_id(entry: Any) -> Any:
        if not isinstance(entry, dict):
            return entry
        entry = {("url" if k == "path" else k): v for k, v in entry.items()}
        if "id" in entry:
            return entry
        named = entry.get("url") or entry.get("title")
        return {"id": str(named), **entry} if isinstance(named, str) else entry

    return {
        **record,
        **{k: [with_id(e) for e in record[k]] for k in ("sources", "contributors") if isinstance(record.get(k), list)},
    }


def _documents(record: dict[str, Any], guide: bool = False) -> dict[str, Any]:
    """``record`` with `docs` (and a schema's `guide`) as `documents`."""
    listed = [record[k] for k in (("guide",) if guide else ()) if record.get(k)]
    listed += [str(d) for d in record.get("docs") or []] if isinstance(record.get("docs"), list) else []
    rest = {k: v for k, v in record.items() if k not in ("docs", *(("guide",) if guide else ()))}
    return {**rest, **({"documents": listed} if listed else {})}


def dataset(record: dict[str, Any]) -> dict[str, Any]:
    """queria.yml as tabledoc.yml. `catalogs` stays; the caller takes it out as `dependencies`."""
    converted = _documents(_ids(_renamed(record, "dataset")))
    written = converted.get("schemas")
    if isinstance(written, list):
        converted["schemas"] = [_documents(s, guide=True) if isinstance(s, dict) else s for s in written]
    return converted


def _semantic(field: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """A field's `semantic` as the column's entity or dimension, or as a metric."""
    semantic = field.get("semantic")
    rest = {k: v for k, v in field.items() if k != "semantic"}
    if not isinstance(semantic, dict):
        return rest, None
    role, name = semantic.get("role"), semantic.get("name")
    if role == "entity":
        return {**rest, **({"entity": name} if name else {})}, None
    if role == "dimension":
        return {**rest, "dimension": "categorical"}, None
    if role == "measure":
        agg = {"agg": semantic["agg"]} if semantic.get("agg") else {}
        return rest, {"name": field.get("name"), **agg, "expr": field.get("name")}
    return rest, None


def table(record: dict[str, Any]) -> dict[str, Any]:
    """A table front matter as a table file. `fields` is `columns`, `semantic` is read as dbt's."""
    own = _documents(_ids(_renamed(record, "table")))
    fields = own.pop("fields", None)
    converted = [
        _semantic(f) if isinstance(f, dict) else (f, None)
        for f in (fields if isinstance(fields, list) else [])
    ]
    metrics = [m for _, m in converted if m is not None]
    return {
        **own,
        **({"columns": [c for c, _ in converted]} if fields is not None else {}),
        **({"metrics": [*(own.get("metrics") or []), *metrics]} if metrics else {}),
    }
