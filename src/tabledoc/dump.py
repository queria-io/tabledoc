"""tabledoc dump: the description a DuckLake catalog holds (`_tabledoc` unless told otherwise) back to the files an author writes.

    tabledoc.yml                    the dataset, the schemas, and the root's other documents
    <schema>/<table>.tabledoc.yml   each table described
    every file of the files table at its path: README.md and the other documents of each folder

Loading the files dump wrote gives the same tables again, but for what they do
not keep: `dependencies` (from dbt's profiles.yml), asset columns (declared to
FDL), and `annotations`.
"""

from __future__ import annotations

import datetime
import hashlib
import posixpath
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import fdl_state, languages, schemas, tables
from .description import README
from .files import normalized
from .load import ALIAS, attached
from .report import SpecError
from .source import DATASET_FILE, TABLE_SUFFIX

#: The keys of tabledoc.yml the `dataset` table holds, in the order they are written.
DATASET_KEYS = ("language", "homepage", "repository", "issued", "update_frequency")


@dataclass(frozen=True)
class Source:
    #: The DuckLake catalog, such as fdl's working metadata.
    catalog: str
    #: Where each file of the files table is, as `<files>/<sha256>`: a folder or an http(s) URL.
    files: str | None = None
    #: The dataset's name in tabledoc.yml.
    name: str | None = None
    #: The schema the description is in.
    schema: str = tables.SCHEMA


def _remote(catalog: str) -> str | None:
    """The repository `fdl clone` made ``catalog`` from, as `fdl status` says; else None."""
    found = fdl_state.status(catalog)
    return found.get("remote") if found else None


def files_base(source: Source) -> str | None:
    """``source.files``, else the assets of the repository `fdl clone` made the catalog from."""
    if source.files:
        return source.files
    remote = _remote(source.catalog)
    return f"{str(remote).rstrip('/')}/assets" if remote else None


def dataset_name(source: Source, held: str | None = None) -> str:
    """``source.name``, else ``held`` (the `name` the dataset table holds), else the last part of
    the repository's URL, else the catalog's file name."""
    if source.name or held:
        return str(source.name or held)
    remote = _remote(source.catalog)
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


def _documents(paths: list[str], folder: str) -> list[str]:
    """The Markdown files directly in ``folder``, README.md first: that folder's documents.
    The root's README.md is the dataset's without being listed."""
    found = [
        p
        for p in paths
        if posixpath.dirname(p) == folder and p.lower().endswith(".md") and (folder or posixpath.basename(p) != README)
    ]
    return sorted(found, key=lambda p: posixpath.basename(p) != README)


Where = tuple[str, str, str]


def _at(row: dict[str, Any]) -> Where:
    return (row.get("schema_name") or "", row.get("table_name") or "", row.get("column_name") or "")


def _texts(found: tables.Rows, language: str) -> dict[Where, dict[str, Any]]:
    """`descriptions`, `topics` and `synonyms` by what they describe: as the text alone when it is
    written in the dataset's `language` only, else as a map from the language to the text."""
    by_where: dict[Where, dict[str, dict[str, Any]]] = {}
    for row in found.get("descriptions") or []:
        for key in tables.TEXTS:
            if row.get(key) not in (None, ""):
                by_where.setdefault(_at(row), {}).setdefault(key, {})[row["language"]] = row[key]
    for table, key, column in (("topics", "topics", "topic"), ("synonyms", "synonyms", "synonym")):
        for row in found.get(table) or []:
            words = by_where.setdefault(_at(row), {}).setdefault(key, {})
            words.setdefault(row["language"], []).append(row[column])
    for keys in by_where.values():
        # The tables keep no order for words: sorted, so the same tables give the same files.
        for key in ("topics", "synonyms"):
            for words in (keys.get(key) or {}).values():
                words.sort()
    return {
        where: {
            k: next(iter(v.values())) if [t.lower() for t in v] == [language.lower()] else dict(sorted(v.items()))
            for k in ("title", "title_reading", "description", "topics", "synonyms")
            if (v := keys.get(k))
        }
        for where, keys in by_where.items()
    }


def _ordered(found: tables.Rows, table: str, column: str) -> dict[tuple[str, str], list[Any]]:
    """The values of ``column`` of ``table`` by (schema, table), in the order of `position`."""
    rows = sorted(found.get(table) or [], key=lambda r: (r["schema_name"], r["table_name"], r.get("position", 0)))
    grouped: dict[tuple[str, str], list[Any]] = {}
    for r in rows:
        grouped.setdefault((r["schema_name"], r["table_name"]), []).append(r[column])
    return grouped


class _Entries:
    """Licenses or sources as the files write them: in full where an id is first used, by
    its id alone after that. A license that has only its id is written as the id."""

    def __init__(self, rows: list[dict[str, Any]], bare: bool) -> None:
        self.by_id = {r["id"]: _plain(r) for r in rows}
        self.bare = bare
        self.written: set[str] = set()

    def __call__(self, ids: list[str]) -> list[Any]:
        out: list[Any] = []
        for i in ids:
            entry = self.by_id.get(i, {"id": i})
            if i in self.written or (self.bare and set(entry) == {"id"}):
                out.append(i)
            else:
                out.append(entry)
            self.written.add(i)
        return out


def _on(at: tuple[str, str], found: tables.Rows, licenses: _Entries, sources: _Entries) -> dict[str, Any]:
    """`licenses`, `sources` and `spatial_coverage` of the dataset (``at`` is ('', '')) or of a table."""
    lic = _ordered(found, "table_licenses", "license_id").get(at)
    src = _ordered(found, "table_sources", "source_id").get(at)
    areas = _ordered(found, "table_areas", "area").get(at)
    return {
        **({"licenses": licenses(lic)} if lic else {}),
        **({"sources": sources(src)} if src else {}),
        **({"spatial_coverage": areas} if areas else {}),
    }


def _temporal(start: Any, end: Any) -> dict[str, Any]:
    coverage = {k: v for k, v in (("start", start), ("end", end)) if v is not None}
    return {"temporal_coverage": coverage} if coverage else {}


def _column(row: dict[str, Any], text: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row["column_name"],
        **text,
        **({"entity": row["entity"]} if row.get("entity") else {}),
        **({"dimension": row["dimension"]} if row.get("dimension") else {}),
        **({"granularity": row["granularity"]} if row.get("granularity") else {}),
    }


def _metric(row: dict[str, Any]) -> dict[str, Any]:
    return {"name": row["metric_name"], **{k: row[k] for k in ("agg", "expr", "description") if row.get(k)}}


def documents(found: tables.Rows, name: str) -> dict[str, dict[str, Any]]:
    """The YAML files of the description in ``found``, by path."""
    values = {r["key"]: r["value"] for r in found.get("dataset") or []}
    language = str(values.get("language") or languages.UNDETERMINED)
    texts = _texts(found, language)
    licenses = _Entries(found.get("licenses") or [], bare=True)
    sources = _Entries(found.get("sources") or [], bare=False)
    paths = sorted(f["path"] for f in found.get("files") or [])
    columns = found.get("columns") or []
    metrics = found.get("metrics") or []
    depends = {at: sorted(d) for at, d in _ordered(found, "table_dependencies", "depends_on").items()}
    roles: dict[str, list[str]] = {}
    for r in sorted(found.get("contributor_roles") or [], key=lambda r: (r["contributor_id"], r["role"])):
        roles.setdefault(r["contributor_id"], []).append(r["role"])
    contributors = [
        {**_plain({k: c.get(k) for k in ("id", "title", "url")}), **({"roles": roles[c["id"]]} if c["id"] in roles else {})}
        for c in sorted(found.get("contributors") or [], key=lambda c: c.get("position", 0))
    ]
    dataset = {
        **texts.get(("", "", ""), {}),
        **{k: values[k] for k in DATASET_KEYS if k in values},
        **_on(("", ""), found, licenses, sources),
        **({"contributors": contributors} if contributors else {}),
        **_temporal(values.get("temporal_start"), values.get("temporal_end")),
        **({"image": values["image"]} if values.get("image") else {}),
    }
    written: dict[str, dict[str, Any]] = {}
    described_tables = sorted(found.get("tables") or [], key=lambda t: (t["schema_name"], t["table_name"]))
    for table in described_tables:
        schema, table_name = table["schema_name"], table["table_name"]
        own = [c for c in columns if (c["schema_name"], c["table_name"]) == (schema, table_name)]
        own_metrics = [m for m in metrics if (m["schema_name"], m["table_name"]) == (schema, table_name)]
        authored = not table.get("source_path")
        keyed = sorted((c for c in own if c.get("key_position") is not None), key=lambda c: c["key_position"])
        own = [c for c in own if set(c) - {"schema_name", "table_name", "column_name", "key_position"} or _at(c) in texts]
        record = {
            **texts.get((schema, table_name, ""), {}),
            **({"hidden": True} if table.get("hidden") is True else {}),
            **({"primary_key": [c["column_name"] for c in keyed]} if keyed else {}),
            **_on((schema, table_name), found, licenses, sources),
            **_temporal(table.get("temporal_start"), table.get("temporal_end")),
            **({"sql": table["sql"]} if authored and table.get("sql") else {}),
            **({"depends_on": depends[(schema, table_name)]} if authored and (schema, table_name) in depends else {}),
        }
        docs = _documents(paths, f"{schema}/{table_name}")
        if set(record) == {"hidden"} and not (own or own_metrics or docs):
            continue  # a row `load --hide-undescribed` wrote for a table with no description
        written[f"{schema}/{table_name}{TABLE_SUFFIX}"] = {
            "$schema": schemas.TABLE,
            **record,
            **({"documents": docs} if docs else {}),
            **({"columns": [_column(c, texts.get(_at(c), {})) for c in own]} if own else {}),
            **({"metrics": [_metric(m) for m in own_metrics]} if own_metrics else {}),
        }
    names = sorted({r["schema_name"] for r in found.get("schemas") or []} | {t["schema_name"] for t in described_tables})
    schema_list = [
        {"name": s, **texts.get((s, "", ""), {}), **({"documents": d} if d else {})}
        for s in names
        if (d := _documents(paths, s)) or (s, "", "") in texts
    ]
    docs = _documents(paths, "")
    return {
        DATASET_FILE: {
            "$schema": schemas.DATASET,
            "name": name,
            **dataset,
            **({"schemas": schema_list} if schema_list else {}),
            **({"documents": docs} if docs else {}),
        },
        **written,
    }


def _held_name(found: tables.Rows) -> str | None:
    return next((r["value"] for r in found.get("dataset") or [] if r.get("key") == "name"), None)


class _Dumper(yaml.SafeDumper):
    pass


def _text(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _text)


def render(record: dict[str, Any]) -> str:
    return yaml.dump(record, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=120)


def dump(source: Source, out: Path, *, force: bool = False) -> list[str]:
    """Write the files of the description in ``source``'s schema under ``out``; their paths.

    Refused when one of them is already there, unless ``force``.
    """
    if ".fdl" in out.resolve().parts:
        raise SpecError(f"{out} is inside .fdl/, which only fdl writes; give a folder outside it")
    import duckdb

    try:
        with attached(source.catalog, None, read_only=True) as con:
            held_in = tables.spelled_schema(con, ALIAS, source.schema)
            found = tables.read(con, ALIAS, held_in)
    except duckdb.Error as exc:
        raise SpecError(f"cannot read {source.schema} in {source.catalog}: {exc}") from exc
    if not found:
        raise SpecError(f"{source.catalog} has no {source.schema} schema")
    if (
        any("key" not in r for r in found.get("dataset") or [])
        or any("schema_name" not in r or "listed" in r for r in found.get("tables") or [])
        or any("path" in r for k in ("sources", "contributors") for r in found.get(k) or [])
        or any("spdx" in r for r in found.get("licenses") or [])
    ):
        raise SpecError(
            f"{source.schema} in {source.catalog} is in an earlier tabledoc's tables; "
            "dump it with the tabledoc that wrote it, or load the description again first"
        )
    texts = {
        path: render(record).encode("utf-8")
        for path, record in documents(found, dataset_name(source, _held_name(found))).items()
    }
    entries = sorted(found.get("files") or [], key=lambda f: f["path"])
    for path in [*texts, *(f["path"] for f in entries)]:
        if normalized(path) != path:
            raise SpecError(f"{source.catalog} names the file {path}, which is not a path under {out}")
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
