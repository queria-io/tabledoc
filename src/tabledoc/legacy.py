"""The formats before tabledoc, read as tabledoc's.

- queria.yml (https://queria.io/schemas/dataset/v1.json) as tabledoc.yml, with
  Queria's keys at the top level
- Markdown whose front matter is https://queria.io/schemas/table/v1.json, as a
  table file (the front matter) and its guide (the text below)
"""

from __future__ import annotations

import re
from typing import Any

from .shape import QUERIA

DATASET_FILE = "queria.yml"
#: Keys queria.yml wrote at the top level that tabledoc.yml writes under `queria:`.
QUERIA_KEYS = {
    "dataset": ("title_kana", "themes", "cover", "ai_context"),
    "table": ("published", "themes", "ai_context"),
}

_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?\r?\n)?---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.DOTALL)


def split_front_matter(text: str) -> tuple[str, str] | None:
    """(front matter, body) of a Markdown file, or None when it has none."""
    match = _FRONT_MATTER.match(text)
    return (match.group(1) or "", match.group(2)) if match else None


def _queria(record: dict[str, Any], level: str) -> dict[str, Any]:
    """``record`` with Queria's top-level keys, and annotations.queria, under `queria:`."""
    keys = QUERIA_KEYS[level]
    written = record.get("annotations") if isinstance(record.get("annotations"), dict) else {}
    own = {
        **(written.get(QUERIA) or {}),
        **{k: v for k, v in record.items() if k in keys},
    }
    others = {k: v for k, v in written.items() if k != QUERIA}
    rest = {k: v for k, v in record.items() if k not in keys and k != "annotations"}
    return {
        **rest,
        **({QUERIA: own} if own else {}),
        **({"annotations": others} if others else {}),
    }


def dataset(record: dict[str, Any]) -> dict[str, Any]:
    """queria.yml as tabledoc.yml. `catalogs` stays; the caller takes it out."""
    return _queria(record, "dataset")


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
    own = _queria(record, "table")
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
