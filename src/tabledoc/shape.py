"""Records as a Description holds them, from what an author wrote.

Every reader of a description (table files, the older formats, dbt) turns it
into a record in the table file's form first; the functions here turn that
form into one. Keys come out in a fixed order, so the
same input gives the same records.
"""

from __future__ import annotations

import datetime
from typing import Any

DATASET_KEYS = (
    "name",
    "schema",
    "title",
    "title_reading",
    "description",
    "topics",
    "synonyms",
    "homepage",
    "repository",
    "language",
    "issued",
    "update_frequency",
    "licenses",
    "sources",
    "contributors",
    "temporal_coverage",
    "spatial_coverage",
    "image",
)
SCHEMA_KEYS = ("name", "title", "title_reading", "description", "topics", "synonyms")
TABLE_KEYS = (
    "title",
    "title_reading",
    "description",
    "topics",
    "synonyms",
    "listed",
    "primary_key",
    "licenses",
    "sources",
    "temporal_coverage",
    "spatial_coverage",
    "materialized",
    "sql",
    "depends_on",
    "source_path",
)
#: What dbt fills in from the build, not what the author writes.
BUILT_KEYS = ("materialized", "sql", "depends_on", "source_path")
COLUMN_KEYS = ("name", "title", "title_reading", "description", "topics", "synonyms", "asset")
METRIC_KEYS = ("name", "agg", "expr", "description")


def present(value: Any) -> bool:
    return value is not None and value != ""


def plain(value: Any) -> Any:
    """``value`` with the dates YAML reads (`issued: 2026-10-30`) as the text that was written."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def pick(record: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """``keys`` of ``record``. `keywords`, the earlier name, is read as `topics` when `topics` is not written."""
    if "topics" in keys and "topics" not in record and present(record.get("keywords")):
        record = {**record, "topics": record["keywords"]}
    return {k: plain(record[k]) for k in keys if k in record and present(record[k])}


def annotations(record: dict[str, Any]) -> dict[str, Any]:
    """`annotations`: keys for other readers, by the reader's name."""
    written = record.get("annotations")
    return {"annotations": plain(written)} if isinstance(written, dict) and written else {}


def typed(value: Any) -> dict[str, Any] | None:
    """An entity or dimension as {type, name}: `categorical` becomes {"type": "categorical"}."""
    if isinstance(value, str) and value:
        return {"type": value}
    if isinstance(value, dict) and value.get("type"):
        return {"type": value["type"], **({"name": value["name"]} if value.get("name") else {})}
    return None


def column(record: dict[str, Any]) -> dict[str, Any]:
    semantic = {
        key: shaped
        for key in ("entity", "dimension")
        if (shaped := typed(record.get(key))) is not None
    }
    granularity = {"granularity": record["granularity"]} if present(record.get("granularity")) else {}
    return {**pick(record, COLUMN_KEYS), **semantic, **granularity, **annotations(record)}


def table(record: dict[str, Any]) -> dict[str, Any]:
    """A table's description, without schema, name and guide."""
    columns = [column(c) for c in record.get("columns") or [] if isinstance(c, dict)]
    metrics = [pick(m, METRIC_KEYS) for m in record.get("metrics") or [] if isinstance(m, dict)]
    return {
        **pick(record, TABLE_KEYS),
        **({"columns": columns} if columns else {}),
        **({"metrics": metrics} if metrics else {}),
        **annotations(record),
    }


def described(record: dict[str, Any]) -> bool:
    """Whether ``record`` says anything an author writes, beyond the SQL dbt fills in."""
    shaped = table(record)
    return bool(set(shaped) - set(BUILT_KEYS))
