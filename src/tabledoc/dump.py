"""tabledoc dump: the `_fdl` schema of a DuckLake catalog back to the files an author writes.

    tabledoc.yml                  the dataset, the schemas, and the root's other documents
    <schema>/<table>.yml          each table described
    every file of _fdl.files      at its path: README.md and the other documents of each folder

Loading the files dump wrote gives the same `_fdl` again, but for what `_fdl`
does not keep: an entity's type (written `primary` for a column that alone is
the primary key, else `foreign`), dimensions, granularity, metrics, and
`catalogs`, which come from dbt's profiles.yml.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import posixpath
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import fdl, schemas
from .description import README
from .load import ALIAS, attached, data_path
from .report import SpecError
from .shape import QUERIA
from .source import DATASET_FILE

DATASET_KEYS = (
    "title",
    "description",
    "language",
    "topics",
    "homepage",
    "issued",
    "update_frequency",
    "licenses",
    "sources",
    "contributors",
    "temporal_coverage",
    "spatial_coverage",
)
TABLE_KEYS = ("title", "description", "topics", "primary_key", "licenses", "sources", "temporal_coverage", "spatial_coverage")


@dataclass(frozen=True)
class Source:
    #: The DuckLake catalog: a .sqlite or .duckdb file, or a ducklake: path.
    catalog: str
    #: Where each file of `_fdl.files` is, as `<files>/<sha256>`: a folder or an http(s) URL.
    files: str | None = None
    #: The dataset's name in tabledoc.yml.
    name: str | None = None


def _note(catalog: str) -> dict[str, Any]:
    note = Path(catalog.removeprefix("ducklake:") + ".fdl.json")
    try:
        found = json.loads(note.read_text(encoding="utf-8")) if note.is_file() else {}
    except (OSError, ValueError) as exc:
        raise SpecError(f"cannot read {note}: {exc}") from exc
    return found if isinstance(found, dict) else {}


def files_base(source: Source) -> str | None:
    """``source.files``, else the assets of the repository `fdl clone` noted beside the catalog."""
    if source.files:
        return source.files
    remote = _note(source.catalog).get("remote")
    return f"{str(remote).rstrip('/')}/assets" if remote else None


def dataset_name(source: Source) -> str:
    """``source.name``, else the last part of the repository's URL, else the catalog's file name."""
    if source.name:
        return source.name
    remote = _note(source.catalog).get("remote")
    if remote:
        return posixpath.basename(str(remote).rstrip("/"))
    return Path(source.catalog.removeprefix("ducklake:")).name.split(".")[0]


def fetch(base: str, sha256: str) -> bytes:
    """The file whose content has ``sha256``, from ``base``; checked against it."""
    location = f"{base.rstrip('/')}/{sha256}"
    try:
        if location.startswith(("http://", "https://")):
            with urllib.request.urlopen(location, timeout=60) as response:
                body = response.read()
        elif "://" in location:
            raise SpecError(f"cannot read {location}; give a folder or an http(s) URL with --files")
        else:
            body = Path(location).read_bytes()
    except OSError as exc:
        raise SpecError(f"cannot read {location}: {exc}") from exc
    if hashlib.sha256(body).hexdigest() != sha256:
        raise SpecError(f"{location} does not hold the file whose sha256 is {sha256}")
    return body


def _plain(value: Any) -> Any:
    """``value`` as YAML writes it: no NULL fields, dates as text."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _fields(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    picked = {k: _plain(row[k]) for k in keys if row.get(k) not in (None, "", [])}
    licenses = picked.get("licenses")
    if licenses:
        picked["licenses"] = [lic["id"] if set(lic) == {"id"} else lic for lic in licenses]
    return picked


def _readers(attributes: list[dict[str, Any]]) -> dict[str, Any]:
    """`queria:` and `annotations:` of one thing, from its rows of `_fdl.attributes`."""
    found: dict[str, dict[str, Any]] = {}
    for row in sorted(attributes, key=lambda r: r["key"]):
        reader, key = fdl.split_key(row["key"])
        found.setdefault(reader, {})[key] = row["value"]
    others = {k: v for k, v in found.items() if k != QUERIA}
    return {**({QUERIA: found[QUERIA]} if QUERIA in found else {}), **({"annotations": others} if others else {})}


def _documents(paths: list[str], folder: str) -> list[str]:
    """The Markdown files directly in ``folder`` but its README.md: that folder's documents."""
    return [
        p
        for p in paths
        if posixpath.dirname(p) == folder and p.lower().endswith(".md") and posixpath.basename(p) != README
    ]


def _column(row: dict[str, Any], primary_key: list[str], attributes: list[dict[str, Any]]) -> dict[str, Any]:
    entity = row.get("entity")
    kind = "primary" if primary_key == [row["name"]] else "foreign"
    return {
        "name": row["name"],
        **_fields(row, ("title", "description")),
        **({"entity": {"type": kind, "name": entity}} if entity else {}),
        **({"asset": True} if row.get("asset") else {}),
        **_readers(attributes),
    }


def _unlisted_only(table: dict[str, Any], attributes: list[dict[str, Any]], columns: list[Any]) -> bool:
    """A row `load --unlisted` writes for a table with no description, and nothing else."""
    said = {k for k, v in table.items() if v is not None and k not in ("schema", "name", "profile")}
    keys = [a["key"] for a in attributes]
    return not said and not columns and keys == [fdl.attribute_key(QUERIA, "published")]


def documents(found: fdl.Rows, name: str) -> dict[str, dict[str, Any]]:
    """The YAML files of the description in ``found``, by path."""
    paths = sorted(f["path"] for f in found.get("files") or [])
    attributes = found.get("attributes") or []

    def of(schema: str = "", table: str = "", column: str = "") -> list[dict[str, Any]]:
        return [a for a in attributes if (a["schema"], a["table"], a["column"]) == (schema, table, column)]

    tables = sorted(found.get("tables") or [], key=lambda t: (t["schema"], t["name"]))
    columns = found.get("columns") or []
    written: dict[str, dict[str, Any]] = {}
    for table in tables:
        schema, table_name = table["schema"], table["name"]
        own = [c for c in columns if (c["schema"], c["table"]) == (schema, table_name)]
        if _unlisted_only(table, of(schema, table_name), own):
            continue
        key = list(table.get("primary_key") or [])
        docs = _documents(paths, f"{schema}/{table_name}")
        authored = not table.get("source_path")
        written[f"{schema}/{table_name}.yml"] = {
            "$schema": schemas.TABLE,
            **_fields(table, TABLE_KEYS),
            **({"sql": table["sql"]} if authored and table.get("sql") else {}),
            **({"depends_on": list(table["depends_on"])} if authored and table.get("depends_on") else {}),
            **({"docs": docs} if docs else {}),
            **(
                {"columns": [_column(c, key, of(schema, table_name, c["name"])) for c in own]}
                if own
                else {}
            ),
            **_readers(of(schema, table_name)),
        }
    described = {s["schema"]: s for s in found.get("schemas") or []}
    names = sorted(set(described) | {t["schema"] for t in tables})
    schema_list = [
        {"name": s, **_fields(described.get(s, {}), ("title", "description")), **({"docs": d} if d else {})}
        for s in names
        if (d := _documents(paths, s)) or s in described
    ]
    dataset = (found.get("dataset") or [{}])[0]
    docs = _documents(paths, "")
    return {
        DATASET_FILE: {
            "$schema": schemas.DATASET,
            "name": name,
            **_fields(dataset, DATASET_KEYS),
            **({"schemas": schema_list} if schema_list else {}),
            **({"docs": docs} if docs else {}),
            **_readers(of()),
        },
        **written,
    }


class _Dumper(yaml.SafeDumper):
    pass


def _text(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _text)


def render(record: dict[str, Any]) -> str:
    return yaml.dump(record, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=120)


def dump(source: Source, out: Path, *, force: bool = False) -> list[str]:
    """Write the files of the description in ``source``'s `_fdl` under ``out``; their paths.

    Refused when one of them is already there, unless ``force``.
    """
    import duckdb

    if ".fdl" in out.resolve().parts:
        raise SpecError(f"{out} is inside .fdl/, which only fdl writes; give a folder outside it")
    try:
        with attached(source.catalog, data_path(source.catalog, None)) as con:
            found = fdl.read(con, ALIAS)
    except duckdb.Error as exc:
        raise SpecError(f"cannot read {fdl.SCHEMA} in {source.catalog}: {exc}") from exc
    if found is None:
        raise SpecError(f"{source.catalog} has no {fdl.SCHEMA} schema")
    texts = {path: render(record).encode("utf-8") for path, record in documents(found, dataset_name(source)).items()}
    entries = sorted(found.get("files") or [], key=lambda f: f["path"])
    clash = sorted(p for p in [*texts, *(f["path"] for f in entries)] if (out / p).exists())
    if clash and not force:
        raise SpecError(f"{', '.join(clash)} already in {out}; give --force to replace them")
    base = files_base(source)
    if entries and base is None:
        raise SpecError("give where the files are: --files, or a catalog fdl clone made")
    for path, body in [*texts.items(), *((f["path"], fetch(base or "", f["sha256"])) for f in entries)]:
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    return sorted([*texts, *(f["path"] for f in entries)])
