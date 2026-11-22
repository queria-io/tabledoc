"""Text written in more than one language.

An author writes text as the text alone, in the dataset's `language`, or as a map
from a BCP 47 tag to the text. A Description holds it as the map always.
"""

from __future__ import annotations

from typing import Any

#: The tag of text whose language is not known (no `language` in tabledoc.yml).
UNDETERMINED = "und"

#: Keys whose value is text, of each kind of record.
DATASET = ("title", "description", "topics", "homepage")
SCHEMA = ("title", "description")
TABLE = ("title", "description", "topics")
COLUMN = ("title", "description")
METRIC = ("description",)
#: Keys of an entry of `licenses`, `sources` and `contributors`.
ENTRY = ("title", "url", "path")
LISTS = ("licenses", "sources", "contributors")


def _present(value: Any) -> bool:
    return value not in (None, "", [])


def as_map(value: Any, language: str) -> dict[str, Any] | None:
    """``value`` as {tag: text}: the text alone is in ``language``."""
    if isinstance(value, dict):
        return {str(tag): text for tag, text in value.items() if _present(text)} or None
    return {language: value} if _present(value) else None


def one(value: Any, language: str) -> Any:
    """The text of ``value`` in ``language``, else the undetermined one, else the first by tag."""
    if not isinstance(value, dict):
        return value
    by_tag = {tag.lower(): text for tag, text in sorted(value.items(), reverse=True)}
    for tag in (language, UNDETERMINED, *sorted(value)):
        if tag.lower() in by_tag:
            return by_tag[tag.lower()]
    return None


def _keys(record: dict[str, Any], keys: tuple[str, ...], language: str) -> dict[str, Any]:
    shaped = {k: as_map(v, language) if k in keys else v for k, v in record.items()}
    return {k: v for k, v in shaped.items() if v is not None}


def _entries(record: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        **record,
        **{
            k: [_keys(e, ENTRY, language) if isinstance(e, dict) else e for e in record[k]]
            for k in LISTS
            if isinstance(record.get(k), list)
        },
    }


def dataset(record: dict[str, Any], language: str) -> dict[str, Any]:
    return _entries(_keys(record, DATASET, language), language)


def schema(record: dict[str, Any], language: str) -> dict[str, Any]:
    return _keys(record, SCHEMA, language)


def table(record: dict[str, Any], language: str) -> dict[str, Any]:
    shaped = _entries(_keys(record, TABLE, language), language)
    return {
        **shaped,
        **({"columns": [_keys(c, COLUMN, language) for c in shaped["columns"]]} if "columns" in shaped else {}),
        **({"metrics": [_keys(m, METRIC, language) for m in shaped["metrics"]]} if "metrics" in shaped else {}),
    }


def several(value: Any) -> bool:
    """Whether ``value`` is a map with more than one language."""
    return isinstance(value, dict) and len(value) > 1
