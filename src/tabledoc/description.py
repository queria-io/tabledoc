"""A dataset's description, read from what an author wrote under the root."""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import dbt, files, git, lineage, shape, source
from .report import Report

README = "README.md"
DEFAULT_MANIFEST = Path("target") / "manifest.json"


@dataclass(frozen=True)
class Options:
    root: Path
    #: dbt's manifest.json; default target/manifest.json in a dbt project.
    manifest: Path | None = None
    #: dbt's profiles.yml, for the other datasets the SQL reads; default DBT_PROFILES_DIR or the root.
    profiles: Path | None = None
    #: Whether to say where it came from (`source`). Off for comparing outputs.
    with_source: bool = True


@dataclass(frozen=True)
class Description:
    """What the author wrote, with the older formats read as today's.

    Records are plain dicts and lists, keys in a fixed order. Guides and the
    files they link to are named by path; ``files`` lists each with its sha256,
    and ``content`` gives what to send for one.
    """

    root: Path
    dataset: dict[str, Any]
    schemas: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    files: list[files.File]
    #: The Git working copy around the root; None outside Git or without ``with_source``.
    source: dict[str, Any] | None = None
    #: Alias -> repository URL of each other dataset the SQL reads (from dbt's profiles.yml).
    catalogs: dict[str, str] | None = None

    def content(self, file: files.File) -> bytes:
        """What goes into the dataset for ``file``: its bytes, with a Markdown document's
        relative links following the files that moved."""
        return files.body(self.root, file, {f.local: f.path for f in self.files})


MANIFEST_MISSING = "manifest-missing"


def _profiles(options: Options) -> dict[str, Any]:
    import os

    folder = os.environ.get("DBT_PROFILES_DIR")
    path = options.profiles or (Path(folder) if folder else options.root) / "profiles.yml"
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _dbt_tables(options: Options, report: Report) -> tuple[list[source.Table], dict[str, str]]:
    root = options.root
    if not (root / "dbt_project.yml").is_file():
        return [], {}
    path = options.manifest or root / DEFAULT_MANIFEST
    if not path.is_file():
        report.warning(
            MANIFEST_MISSING,
            f"{path} is not here, so dbt's models are not read; run dbt compile first",
            root / "dbt_project.yml",
        )
        return [], dbt.catalogs(_profiles(options))
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return dbt.tables(manifest, root, report), dbt.catalogs(_profiles(options))


def _merge(
    built: list[source.Table], written: list[source.Table], report: Report
) -> list[source.Table]:
    """One table per (schema, name). A table is described in one place only."""
    by_key: dict[source.Key, source.Table] = {}
    for table in written:
        if table.key in by_key:
            report.error(
                "described-twice",
                f"{table.schema}.{table.name} is also described in {by_key[table.key].path}",
                table.path,
            )
            continue
        by_key[table.key] = table
    merged = dict(by_key)
    for model in built:
        found = by_key.get(model.key)
        if found is None:
            merged[model.key] = model
            continue
        if shape.described(model.record):
            report.error(
                "described-twice",
                f"{model.schema}.{model.name} is described in dbt's yml and in {found.path}; keep one",
                model.path,
            )
        built = {k: model.record[k] for k in shape.BUILT_KEYS if k in model.record and k not in found.record}
        merged[model.key] = source.Table(
            found.schema,
            found.name,
            record={**found.record, **built},
            path=found.path,
            guide=found.guide or model.guide,
        )
    return [merged[k] for k in sorted(merged)]


def _warn_metrics(tables: list[source.Table], report: Report) -> None:
    for table in tables:
        for metric in table.record.get("metrics") or []:
            if isinstance(metric, dict) and not metric.get("agg"):
                report.warning(
                    "metric-without-agg", f"{table.schema}.{table.name}: metric {metric.get('name')} has no agg", table.path
                )


def _table(table: source.Table) -> dict[str, Any]:
    shaped = shape.table(table.record)
    head = {k: shaped[k] for k in shape.TABLE_KEYS if k in shaped}
    tail = {k: v for k, v in shaped.items() if k not in shape.TABLE_KEYS}
    docs = table.record.get("docs")
    return {
        "schema": table.schema,
        "name": table.name,
        **head,
        **({"guide": table.guide} if table.guide else {}),
        **({"docs": [str(d) for d in docs]} if isinstance(docs, list) and docs else {}),
        **tail,
    }


def _schemas(record: dict[str, Any], tables: list[source.Table], root: Path) -> list[dict[str, Any]]:
    """The schemas of tabledoc.yml, and each other schema whose folder holds a README.md.

    `guide` and `docs` stay as written (paths under the root) until ``_place``.
    """
    written = record.get("schemas")
    listed = [
        {
            **shape.pick(s, shape.SCHEMA_KEYS),
            **({"guide": s["guide"]} if s.get("guide") else {}),
            **({"docs": [str(d) for d in s["docs"]]} if isinstance(s.get("docs"), list) and s["docs"] else {}),
        }
        for s in (written if isinstance(written, list) else [])
        if isinstance(s, dict) and s.get("name")
    ]
    names = {s["name"] for s in listed}
    others = [{"name": n} for n in sorted({t.schema for t in tables} - names)]
    return [
        {**s, "guide": f"{s['name']}/{README}"} if "guide" not in s and (root / s["name"] / README).is_file() else s
        for s in listed + others
    ]


def _local(entry: Any, root: Path, where: Path, report: Report) -> str | None:
    path = files.normalized(str(entry))
    if path is None:
        report.error("file-outside", f"{entry} is outside {root}", where)
    return path


def _place(
    record: dict[str, Any], folder: str, root: Path, where: Path, report: Report, named: list[tuple[str, str, Path]]
) -> dict[str, Any]:
    """``record`` with its `guide` and `docs` at their paths in the dataset: the guide is
    ``folder``/README.md, and each document goes into ``folder`` by its file name."""
    prefix = f"{folder}/" if folder else ""
    guide = _local(record["guide"], root, where, report) if record.get("guide") else None
    docs = [d for d in (_local(e, root, where, report) for e in record.get("docs") or []) if d]
    if guide:
        named.append((guide, prefix + README, where))
    named.extend((d, prefix + posixpath.basename(d), where) for d in docs)
    placed = {k: v for k, v in record.items() if k not in ("guide", "docs")}
    return {
        **placed,
        **({"guide": prefix + README} if guide else {}),
        **({"docs": [prefix + posixpath.basename(d) for d in docs]} if docs else {}),
    }


def read(options: Options, report: Report) -> Description:
    """Read and check the description under ``options.root``; findings go to ``report``."""
    root = options.root.resolve()
    options = Options(root, options.manifest, options.profiles, options.with_source)
    dataset = source.read_dataset(root, report)
    models, attached = _dbt_tables(options, report)
    written = [*source.read_table_files(root, report), *source.read_legacy_tables(root, report)]
    tables = _merge(models, written, report)
    _warn_metrics(tables, report)
    record = dataset.record
    named: list[tuple[str, str, Path]] = []
    top = _place(
        {**({"guide": README} if (root / README).is_file() else {}), "docs": record.get("docs") or []},
        "",
        root,
        dataset.path,
        report,
        named,
    )
    schema_list = [_place(s, s["name"], root, dataset.path, report, named) for s in _schemas(record, tables, root)]
    shaped = lineage.fill([_table(t) for t in tables], {**attached, **dataset.catalogs}, report)
    by_key = {t.key: t for t in tables}
    placed_tables = [
        _place(t, f"{t['schema']}/{t['name']}", root, by_key[(t["schema"], t["name"])].path, report, named)
        for t in shaped
    ]
    sent = files.collect(root, named, report)
    return Description(
        root=root,
        dataset={
            **shape.pick(record, shape.DATASET_KEYS),
            **top,
            **shape.annotations(record),
        },
        schemas=[s for s in schema_list if set(s) - {"name"}],
        tables=[_ordered(t) for t in placed_tables],
        files=sent,
        source=git.source(root) if options.with_source else None,
        catalogs={**attached, **dataset.catalogs} or None,
    )


def _ordered(table: dict[str, Any]) -> dict[str, Any]:
    """Keys in a fixed order: depends_on, filled in last, after sql; guide and docs, placed last, before columns."""
    order = ["schema", "name", *shape.TABLE_KEYS, "guide", "docs", "columns", "metrics", "annotations"]
    return {k: table[k] for k in order if k in table}
