"""The JSON Schemas tabledoc ships, and checking a file against the one it names."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from .report import Report
from .shape import plain

FOLDER = Path(__file__).parent / "schemas"
BASE = "https://queria-io.github.io/tabledoc/schemas/"
DATASET = BASE + "dataset/v1.json"
TABLE = BASE + "table/v1.json"

#: The formats before tabledoc, still read (see legacy.py).
LEGACY_BASE = "https://queria.io/schemas/"
LEGACY_DATASET = LEGACY_BASE + "dataset/v1.json"
LEGACY_TABLE = LEGACY_BASE + "table/v1.json"


@cache
def _registry():
    from referencing import Registry, Resource

    resources = [
        Resource.from_contents(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(FOLDER.rglob("*.json"))
    ]
    return Registry().with_resources((r.contents["$id"], r) for r in resources)


def check(record: Any, schema_id: str, path: Path | None, report: Report) -> None:
    """``record`` against the schema ``schema_id``, one error per violation.

    Dates YAML reads (`issued: 2026-10-30`) are checked as the text that was written.
    """
    import jsonschema

    record = plain(record)
    schema = _registry().get_or_retrieve(schema_id).value.contents
    validator = jsonschema.Draft202012Validator(schema, registry=_registry())
    for error in sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path)):
        location = "/".join(str(p) for p in error.absolute_path) or "(top)"
        report.error("schema-violation", f"{location}: {error.message}", path)
