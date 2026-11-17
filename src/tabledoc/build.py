"""tabledoc.json from what an author wrote under the root."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml

from . import dbt, files, git, lineage, schemas, shape, source
from .report import Report, SpecError

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
class Built:
    document: dict[str, Any]
    files: list[files.File]


def generator() -> str:
    try:
        return f"tabledoc {version('tabledoc')}"
    except PackageNotFoundError:
        return "tabledoc"


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
            "manifest-missing",
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
        sql = {"sql": model.record["sql"]} if "sql" in model.record and "sql" not in found.record else {}
        merged[model.key] = source.Table(
            found.schema,
            found.name,
            record={**found.record, **sql},
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
    return {
        "schema": table.schema,
        "name": table.name,
        **head,
        **({"guide": table.guide} if table.guide else {}),
        **tail,
    }


def _schemas(record: dict[str, Any]) -> list[dict[str, Any]]:
    written = record.get("schemas")
    return [
        {**shape.pick(s, shape.SCHEMA_KEYS), **({"guide": files.normalized(s["guide"])} if s.get("guide") else {})}
        for s in (written if isinstance(written, list) else [])
        if isinstance(s, dict)
    ]


def _documents(
    dataset: source.Dataset, schema_list: list[dict[str, Any]], tables: list[source.Table], root: Path, report: Report
) -> tuple[list[str], list[tuple[str, Path]]]:
    """The dataset's docs as normalized paths, and every document named, with where it is named."""
    written = dataset.record.get("docs")
    docs = []
    for entry in written if isinstance(written, list) else []:
        path = files.normalized(str(entry))
        if path is None:
            report.error("file-outside", f"docs: {entry} is outside {root}", dataset.path)
        else:
            docs.append(path)
    named = [
        *([(README, root / README)] if (root / README).is_file() else []),
        *[(s["guide"], dataset.path) for s in schema_list if s.get("guide")],
        *[(d, dataset.path) for d in docs],
        *[(t.guide, t.path) for t in tables if t.guide],
    ]
    for schema in schema_list:
        if "guide" in schema and schema["guide"] is None:
            report.error("file-outside", f"schemas: {schema['name']}'s guide is outside {root}", dataset.path)
    return docs, [(p, w) for p, w in named if p]


def build(options: Options, report: Report) -> Built:
    root = options.root.resolve()
    options = Options(root, options.manifest, options.profiles, options.with_source)
    dataset = source.read_dataset(root, report)
    models, attached = _dbt_tables(options, report)
    written = [*source.read_table_files(root, report), *source.read_legacy_tables(root, report)]
    tables = _merge(models, written, report)
    _warn_metrics(tables, report)
    schema_list = _schemas(dataset.record)
    docs, named = _documents(dataset, schema_list, tables, root, report)
    sent = files.collect(root, named, report)
    shaped = lineage.fill([_table(t) for t in tables], {**attached, **dataset.catalogs}, report)
    record = dataset.record
    origin = git.source(root) if options.with_source else None
    document = {
        "$schema": schemas.TABLEDOC,
        "generator": generator(),
        **({"source": origin} if origin else {}),
        "dataset": {
            **shape.pick(record, shape.DATASET_KEYS),
            **({"guide": README} if (root / README).is_file() else {}),
            **({"docs": docs} if docs else {}),
            **shape.annotations(record),
        },
        "schemas": schema_list,
        "tables": [_ordered(t) for t in shaped],
        "files": [f.entry() for f in sent],
    }
    schemas.check(document, schemas.TABLEDOC, None, report)
    return Built(document, sent)


def _ordered(table: dict[str, Any]) -> dict[str, Any]:
    """depends_on, filled in last, back in its place after sql."""
    if "depends_on" not in table:
        return table
    order = ["schema", "name", *shape.TABLE_KEYS, "guide", "columns", "metrics", "annotations"]
    return {k: table[k] for k in order if k in table}


def to_json(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpecError(f"{path} is not here; run tabledoc build first") from exc
