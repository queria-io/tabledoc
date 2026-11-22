"""tabledoc export --markdown: the description as Markdown, one file per table, for people and AI to read.

    README.md                     the dataset: what it is, its schemas and tables, then its overview
    <schema>/README.md            each schema: its tables, then its guide
    <schema>/<table>/README.md    each table: columns, semantics, lineage and SQL, then its guide
    every other file of the description at its path in the dataset

The paths are the description's paths in the dataset, so the links in each
guide and document still point at the files they link to. Keys for one
reader (`queria:`, `annotations:`) are not written.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import languages
from .description import README, Description
from .report import SpecError
from .source import EXPORT_MARK

Table = dict[str, Any]


def _cell(value: Any) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _row(cells: Iterable[Any]) -> str:
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _grid(head: list[str], rows: list[list[Any]]) -> list[str]:
    return [_row(head), _row("---" for _ in head), *(_row(r) for r in rows)] if rows else []


def _target(target: Any) -> str:
    """A link destination, in <> when a space or a parenthesis would end it early."""
    text = str(target)
    return f"<{text}>" if re.search(r"[\s()<>]", text) else text


def _link(title: Any, target: Any) -> str:
    return f"[{title or target}]({_target(target)})" if target else str(title or "")


def _value(value: Any) -> str:
    """One metadata value on one line: a link for what has a title and a URL."""
    if isinstance(value, list):
        return ", ".join(_value(v) for v in value)
    if isinstance(value, dict):
        if "start" in value or "end" in value:
            return f"{value.get('start') or ''} – {value.get('end') or ''}".strip()
        named = _link(value.get("title") or value.get("id"), value.get("url") or value.get("path"))
        roles = f" ({', '.join(value['roles'])})" if value.get("roles") else ""
        return named + roles if named else json.dumps(value, ensure_ascii=False)
    return str(value)


FACTS = (
    ("name", "Name"),
    ("primary_key", "Primary key"),
    ("materialized", "Materialized"),
    ("language", "Language"),
    ("topics", "Topics"),
    ("homepage", "Homepage"),
    ("repository", "Repository"),
    ("issued", "Issued"),
    ("update_frequency", "Update frequency"),
    ("licenses", "Licenses"),
    ("sources", "Sources"),
    ("contributors", "Contributors"),
    ("temporal_coverage", "Temporal coverage"),
    ("spatial_coverage", "Spatial coverage"),
    ("source_path", "Built from"),
)
CODE = {"name", "primary_key", "materialized", "source_path"}


def _facts(record: dict[str, Any]) -> list[str]:
    def shown(key: str) -> str:
        value = record[key]
        if key not in CODE:
            return _value(value)
        return ", ".join(f"`{v}`" for v in (value if isinstance(value, list) else [value]))

    return [f"- {label}: {shown(key)}" for key, label in FACTS if record.get(key) not in (None, "", [])]


def _section(title: str, lines: list[str]) -> list[str]:
    return ["", f"## {title}", "", *lines] if lines else []


def _page(lines: list[str]) -> str:
    return "\n".join(lines).strip() + "\n"


def _block(lines: list[str]) -> list[str]:
    return ["", *lines] if lines else []


def _heading(title: Any, name: str) -> str:
    return f"# {title} (`{name}`)" if title else f"# `{name}`"


def _text(description: Any) -> list[str]:
    return ["", str(description).strip()] if description else []


def _summary(description: Any) -> str:
    return re.split(r"\n[ \t]*\n", str(description or "").strip())[0]


def _semantics(column: dict[str, Any]) -> str:
    def typed(key: str) -> str | None:
        value = column.get(key)
        if not value:
            return None
        named = f" ({value['name']})" if value.get("name") else ""
        return f"{key}: {value.get('type')}{named}"

    grain = f"granularity: {column['granularity']}" if column.get("granularity") else None
    asset = "asset: a file of the row" if column.get("asset") else None
    return "; ".join(s for s in (typed("entity"), typed("dimension"), grain, asset) if s)


def _path(schema: str, name: str | None = None) -> str:
    return f"{schema}/{name}/{README}" if name else f"{schema}/{README}"


def _relative(target: str, start: str) -> str:
    return posixpath.relpath(target, posixpath.dirname(start) or ".")


def _key(table: Table) -> str:
    return f"{table['schema']}.{table['name']}"


def _table_link(reference: str, here: str, keys: set[str]) -> str:
    if reference not in keys:
        return f"- `{reference}`"
    schema, name = reference.split(".", 1)
    return f"- [`{reference}`]({_target(_relative(_path(schema, name), here))})"


def _guide(d: Description, path: str | None) -> list[str]:
    """The guide's text after a rule, as written (its links already point at the paths in the dataset)."""
    found = next((f for f in d.files if f.path == path), None) if path else None
    return ["", "---", "", d.content(found).decode("utf-8").strip()] if found else []


def _documents(paths: Iterable[str], here: str) -> list[str]:
    """The documents but the guide (README.md), as links."""
    return [f"- {_link(posixpath.basename(p), _relative(p, here))}" for p in paths if posixpath.basename(p) != README]


def _guide_of(record: dict[str, Any]) -> str | None:
    """The document named README.md: the guide."""
    return next((p for p in record.get("documents") or [] if posixpath.basename(p) == README), None)


def _table(d: Description, table: Table, readers: dict[str, list[str]], keys: set[str]) -> str:
    here = _path(table["schema"], table["name"])
    columns = [[f"`{c['name']}`", c.get("title"), c.get("description"), _semantics(c)] for c in table.get("columns") or []]
    metrics = [[f"`{m['name']}`", m.get("agg"), f"`{m['expr']}`" if m.get("expr") else "", m.get("description")]
               for m in table.get("metrics") or []]
    reads = [_table_link(r, here, keys) for r in table.get("depends_on") or []]
    read_by = [_table_link(r, here, keys) for r in readers.get(_key(table), [])]
    lines = [
        _heading(table.get("title"), _key(table)),
        *_text(table.get("description")),
        *_block(_facts({k: v for k, v in table.items() if k != "name"})),
        *_section("Columns", _grid(["Column", "Title", "Description", "Semantics"], columns)),
        *_section("Metrics", _grid(["Metric", "Aggregation", "Expression", "Description"], metrics)),
        *_section("Reads", reads),
        *_section("Read by", read_by),
        *_section("SQL", ["```sql", str(table["sql"]).strip(), "```"] if table.get("sql") else []),
        *_section("Documents", _documents(table.get("documents") or [], here)),
        *_guide(d, _guide_of(table)),
    ]
    return _page(lines)


def _table_list(tables: list[Table], here: str) -> list[str]:
    return [
        f"- [`{_key(t)}`]({_target(_relative(_path(t['schema'], t['name']), here))})"
        + (f" {t['title']}" if t.get("title") else "")
        + (f": {_summary(t['description'])}" if t.get("description") else "")
        for t in tables
    ]


def _schema(d: Description, schema: dict[str, Any], tables: list[Table]) -> str:
    here = _path(schema["name"])
    lines = [
        _heading(schema.get("title"), schema["name"]),
        *_text(schema.get("description")),
        *_section("Tables", _table_list(tables, here)),
        *_section("Documents", _documents(schema.get("documents") or [], here)),
        *_guide(d, _guide_of(schema)),
    ]
    return _page(lines)


def _dataset(d: Description, schemas: list[dict[str, Any]], tables: list[Table]) -> str:
    def part(schema: dict[str, Any]) -> list[str]:
        title = f"### [{schema.get('title') or schema['name']} (`{schema['name']}`)]({_target(_path(schema['name']))})"
        listed = _table_list([t for t in tables if t["schema"] == schema["name"]], README)
        return ["", title, *_text(_summary(schema.get("description"))), *_block(listed)]

    record = d.dataset
    lines = [
        _heading(record.get("title"), record["name"]),
        *_text(record.get("description")),
        *_block(_facts(record)),
        *(["", "## Tables", *[line for s in schemas for line in part(s)]] if schemas else []),
        *_section("Documents", _documents(record.get("documents") or [], README)),
        *_guide(d, _guide_of(record)),
    ]
    return _page(lines)


def _one(record: dict[str, Any], keys: tuple[str, ...], language: str) -> dict[str, Any]:
    """``record`` with each text of ``keys`` in ``language`` alone (`languages.one`)."""
    flat = {k: languages.one(v, language) if k in keys else v for k, v in record.items()}
    for k in languages.LISTS:
        if isinstance(flat.get(k), list):
            flat[k] = [_one(e, languages.ENTRY, language) if isinstance(e, dict) else e for e in flat[k]]
    for k, inner in (("columns", languages.COLUMN), ("metrics", languages.METRIC)):
        if isinstance(flat.get(k), list):
            flat[k] = [_one(e, inner, language) for e in flat[k]]
    return flat


def _in(d: Description, language: str) -> Description:
    """``d`` with each text in ``language`` alone: one file per table, in the dataset's language."""
    return replace(
        d,
        dataset=_one(d.dataset, languages.DATASET, language),
        schemas=[_one(s, languages.SCHEMA, language) for s in d.schemas],
        tables=[_one(t, languages.TABLE, language) for t in d.tables],
    )


def render(d: Description) -> dict[str, bytes]:
    """Each file to write, by its path in the dataset, in the dataset's `language`."""
    d = _in(d, d.dataset.get("language") or languages.UNDETERMINED)
    tables = d.tables
    keys = {_key(t) for t in tables}
    readers: dict[str, list[str]] = {}
    for t in tables:
        for r in t.get("depends_on") or []:
            readers.setdefault(r, []).append(_key(t))
    written = {s["name"]: s for s in d.schemas}
    schemas = [written.get(n, {"name": n}) for n in sorted({*written, *(t["schema"] for t in tables)})]
    pages = {
        README: _dataset(d, schemas, tables),
        **{_path(s["name"]): _schema(d, s, [t for t in tables if t["schema"] == s["name"]]) for s in schemas},
        **{_path(t["schema"], t["name"]): _table(d, t, readers, keys) for t in tables},
    }
    others = {f.path: d.content(f) for f in d.files if f.path not in pages}
    return {**others, **{p: text.encode("utf-8") for p, text in pages.items()}}


def export(d: Description, out: Path, *, force: bool = False) -> list[str]:
    """Write :func:`render`'s files under ``out``. Refused when one is already there, unless ``force``.

    ``out`` gets a `.tabledoc-export` file, so that reading the root does not read the copies in it.
    """
    if ".fdl" in out.resolve().parts:
        raise SpecError(f"{out} is inside .fdl/, which only fdl writes; give a folder outside it")
    if out.exists() and not out.is_dir():
        raise SpecError(f"{out} is a file; give a folder")
    rendered = render(d)
    clash = sorted(p for p in rendered if (out / p).exists())
    if clash and not force:
        raise SpecError(f"{', '.join(clash)} already in {out}; give --force to replace them")
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / EXPORT_MARK).write_text("written by tabledoc export; tabledoc does not read this folder\n", encoding="utf-8")
        for path, content in sorted(rendered.items()):
            target = out / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    except OSError as exc:
        raise SpecError(f"cannot write {out}: {exc}") from exc
    return sorted(rendered)
