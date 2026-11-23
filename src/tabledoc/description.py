"""A dataset's description, read from what an author wrote under the root."""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import dbt, files, git, languages, licenses, lineage, shape, source
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
    #: The other datasets the SQL reads, by the name it reads them under, as `dependencies`
    #: of FDL's tables.json: ``{name: {"url": …}}`` (from dbt's profiles.yml).
    dependencies: dict[str, dict[str, str]] | None = None

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
        return [], dbt.dependencies(_profiles(options))
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return dbt.tables(manifest, root, report), dbt.dependencies(_profiles(options))


def _merge_columns(
    built: list[dict[str, Any]], written: list[dict[str, Any]], where: str, path: Path, report: Report
) -> list[dict[str, Any]]:
    """Columns by name, key by key: dbt's order first, then the columns only the table file has."""
    entries = [c for c in written if isinstance(c, dict)]
    by_name: dict[Any, int] = {}
    for i, c in enumerate(entries):
        by_name.setdefault(c.get("name"), i)
    used: set[int] = set()
    merged = []
    for column in built:
        i = by_name.get(column.get("name"))
        found = entries[i] if i is not None and i not in used else {}
        if found:
            used.add(i)
        twice = sorted(k for k in set(column) & set(found) if k != "name")
        if twice:
            report.error("described-twice", f"{where}.{column.get('name')}: {', '.join(twice)} also in dbt", path)
        merged.append({**column, **{k: v for k, v in found.items() if k not in column}})
    return merged + [c for i, c in enumerate(entries) if i not in used]


def _merge(
    built: list[source.Table], written: list[source.Table], report: Report
) -> list[source.Table]:
    """One table per (schema, name): what dbt says and what a table file adds, key by key.

    A key written in both is an error; so is a table in two table files."""
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
        where = f"{model.schema}.{model.name}"
        twice = sorted(k for k in set(model.record) & set(found.record) if k not in ("columns", *shape.BUILT_KEYS))
        if twice:
            report.error("described-twice", f"{where}: {', '.join(twice)} also in dbt ({model.path}); keep one", found.path)
        ignored = [k for k in shape.BUILT_KEYS if k in found.record]
        if ignored:
            report.warning("built-by-dbt", f"{where}: {', '.join(ignored)} not read; dbt builds this table", found.path)
        columns = _merge_columns(model.record.get("columns") or [], found.record.get("columns") or [], where, found.path, report)
        record = {
            **{k: v for k, v in found.record.items() if k not in shape.BUILT_KEYS},
            **{k: v for k, v in model.record.items() if k not in found.record or k in shape.BUILT_KEYS},
            **({"columns": columns} if columns else {}),
        }
        if model.guide and found.guide and model.guide != found.guide:
            report.error("guide-twice", f"{where} has two guides: {model.guide} and {found.guide}", found.path)
        merged[model.key] = source.Table(found.schema, found.name, record=record, path=found.path, guide=found.guide or model.guide)
    return [merged[k] for k in sorted(merged)]


def _warn_unlisted(
    root: Path, schema_names: list[str], tables: list[source.Table], listed: set[str], report: Report
) -> None:
    """A README.md where earlier versions found a guide by itself, now that it is not listed."""
    candidates = [Path(n) / README for n in schema_names] + [
        t.path.with_name(source.stem(t.path)).relative_to(root) / README for t in tables if root in t.path.parents
    ]
    for path in candidates:
        if (root / path).is_file() and path.as_posix() not in listed:
            report.warning(
                "unlisted-readme",
                "not read: list it in the documents of what it describes, or move a table's guide to <table>.md",
                root / path,
            )


def _check_dbtignore(root: Path, written: list[source.Table], report: Report) -> None:
    """dbt parses every yml under its model paths; a table file there has to be in .dbtignore."""
    project = root / "dbt_project.yml"
    if not project.is_file():
        return
    loaded = yaml.safe_load(project.read_text(encoding="utf-8"))
    paths = (loaded.get("model-paths") if isinstance(loaded, dict) else None) or ["models"]
    folders = [(root / str(p)).resolve() for p in paths]
    if not any(t.path.name.endswith(source.TABLE_SUFFIX) and any(f in t.path.parents for f in folders) for t in written):
        return
    ignore = root / ".dbtignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    if not any(line.strip().lstrip("/").removeprefix("**/") == f"*{source.TABLE_SUFFIX}" for line in lines):
        report.error("dbtignore", f"add *{source.TABLE_SUFFIX} to .dbtignore, or dbt parses the table files", ignore)


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
    documents = [*([table.guide] if table.guide else []), *_paths(table.record.get("documents"))]
    return {
        "schema": table.schema,
        "name": table.name,
        **head,
        **({"documents": documents} if documents else {}),
        **tail,
    }


def _paths(value: Any) -> list[str]:
    return [str(d) for d in value] if isinstance(value, list) else []


def _schemas(record: dict[str, Any], tables: list[source.Table]) -> list[dict[str, Any]]:
    """The schemas of tabledoc.yml, and each other schema a table is in.

    `documents` stay as written (paths under the root) until ``_place``.
    """
    written = record.get("schemas")
    listed = [
        {
            **shape.pick(s, shape.SCHEMA_KEYS),
            **({"documents": _paths(s["documents"])} if _paths(s.get("documents")) else {}),
        }
        for s in (written if isinstance(written, list) else [])
        if isinstance(s, dict) and s.get("name")
    ]
    names = {s["name"] for s in listed}
    return listed + [{"name": n} for n in sorted({t.schema for t in tables} - names)]


def _local(entry: Any, root: Path, where: Path, report: Report) -> str | None:
    path = files.normalized(str(entry))
    if path is None:
        report.error("file-outside", f"{entry} is outside {root}", where)
    return path


def _place(
    record: dict[str, Any], folder: str, root: Path, where: Path, report: Report, named: list[tuple[str, str, Path]]
) -> dict[str, Any]:
    """``record`` with its `documents` at their paths in the dataset: each goes into
    ``folder`` by its file name, and the first, when it is the guide beside a table
    file or a model (``guide``), as ``folder``/README.md. The README.md comes first."""
    prefix = f"{folder}/" if folder else ""
    guide = record.get("guide")
    documents = [d for d in (_local(e, root, where, report) for e in record.get("documents") or []) if d]
    pairs = [(d, prefix + (README if d == guide else posixpath.basename(d))) for d in documents]
    named.extend((local, placed, where) for local, placed in pairs)
    paths = sorted((p for _, p in pairs), key=lambda p: posixpath.basename(p) != README)
    placed_record = {k: v for k, v in record.items() if k not in ("guide", "documents")}
    return {**placed_record, **({"documents": paths} if paths else {})}


def read(options: Options, report: Report) -> Description:
    """Read and check the description under ``options.root``; findings go to ``report``."""
    root = options.root.resolve()
    options = Options(root, options.manifest, options.profiles, options.with_source)
    dataset = source.read_dataset(root, report)
    models, attached = _dbt_tables(options, report)
    sql = {root / str(m.record["source_path"]): m.key for m in models if m.record.get("source_path")}
    written = [*source.read_table_files(root, report, sql), *source.read_legacy_tables(root, report)]
    _check_dbtignore(root, written, report)
    tables = _merge(models, written, report)
    _warn_metrics(tables, report)
    record = dataset.record
    named: list[tuple[str, str, Path]] = []
    readme = [README] if (root / README).is_file() else []
    top = _place(
        {**({"guide": README} if readme else {}), "documents": readme + _paths(record.get("documents"))},
        "",
        root,
        dataset.path,
        report,
        named,
    )
    image = _local(record["image"], root, dataset.path, report) if shape.present(record.get("image")) else None
    if image:
        # An image keeps its path under the root, as a file a document links to does.
        named.append((image, image, dataset.path))
    schema_list = [_place(s, s["name"], root, dataset.path, report, named) for s in _schemas(record, tables)]
    shaped = lineage.fill([_table(t) for t in tables], {**attached, **dataset.dependencies}, report)
    by_key = {t.key: t for t in tables}
    placed_tables = [
        _place(
            {**t, **({"guide": g} if (g := by_key[(t["schema"], t["name"])].guide) else {})},
            f"{t['schema']}/{t['name']}",
            root,
            by_key[(t["schema"], t["name"])].path,
            report,
            named,
        )
        for t in shaped
    ]
    _warn_unlisted(root, [s["name"] for s in schema_list], tables, {local for local, _, _ in named}, report)
    sent = files.collect(root, named, report)
    language = str(record.get("language") or languages.UNDETERMINED)
    described, listed = _by_id(
        languages.dataset(
            {
                **shape.pick(record, shape.DATASET_KEYS),
                **({"image": image} if image else {}),
                **top,
                **shape.annotations(record),
            },
            language,
        ),
        [languages.table(_ordered(t), language) for t in placed_tables],
        [dataset.path, *(by_key[(t["schema"], t["name"])].path for t in placed_tables)],
        language,
        report,
    )
    return Description(
        root=root,
        dataset=described,
        schemas=[languages.schema(s, language) for s in schema_list if set(s) - {"name"}],
        tables=listed,
        files=sent,
        source=git.source(root) if options.with_source else None,
        dependencies={name: {"url": url} for name, url in sorted({**attached, **dataset.dependencies}.items())} or None,
    )


def _part_of(entry: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether every key of ``entry`` is in ``other`` with the same value."""
    return all(k in other and other[k] == v for k, v in entry.items())


def _by_id(
    dataset: dict[str, Any], tables: list[dict[str, Any]], paths: list[Path], language: str, report: Report
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The dataset and its tables with each license and source written as its id alone, or
    as part of the entry that defines it, replaced by that entry. ``paths`` are the files the
    dataset and each table are described in, for the findings.

    An entry whose keys all match another with the same id (`{id, path}` beside
    `{id, title, path}`, say) is a reference to it; two entries with the same id that
    differ in a key are an error. A license tabledoc knows by its id (CC-BY-4.0, JP-PDL-1.0)
    is tabledoc's entry; another license id nothing defines stays `{id}`; a source id nothing
    defines is an error. Two contributors with the same
    id are an error.
    """
    seen: set[str] = set()
    for c in dataset.get("contributors") or []:
        if isinstance(c, dict) and c.get("id") in seen:
            report.error("defined-twice", f"contributor {c['id']} is written twice", paths[0])
        seen.add(c.get("id") if isinstance(c, dict) else None)
    records = [dataset, *tables]
    for key, single in (("licenses", "license"), ("sources", "source")):
        defined: dict[str, dict[str, Any]] = {}
        for record, where in zip(records, paths):
            for entry in record.get(key) or []:
                # An entry without an id is a schema error already reported.
                if not isinstance(entry, dict) or "id" not in entry:
                    continue
                held = defined.setdefault(entry["id"], entry)
                if _part_of(held, entry):
                    defined[entry["id"]] = entry
                elif not _part_of(entry, held):
                    report.error("defined-twice", f"{single} {entry['id']} is defined twice, differently", where)

        def resolved(entry: Any, where: Path, key: str = key, defined: dict = defined) -> Any:
            if isinstance(entry, dict):
                entry = defined.get(entry.get("id"), entry)
            elif entry in defined:
                entry = defined[entry]
            elif key == "sources":
                report.error("undefined-id", f"source {entry} is not defined; write it with its title and url", where)
                return {"id": entry}
            else:
                entry = {"id": entry}
            return _known(entry, where, language, report) if key == "licenses" else entry

        records = [
            {**r, key: [resolved(e, where) for e in r[key]]} if isinstance(r.get(key), list) else r
            for r, where in zip(records, paths)
        ]
    return records[0], records[1:]


def _known(entry: dict[str, Any], where: Path, language: str, report: Report) -> dict[str, Any]:
    """A license tabledoc knows by its id, as tabledoc knows it; any other as written. Keys
    written that differ from the known ones are dropped with a warning."""
    held = licenses.known(entry, language)
    if held is None:
        return entry
    text = languages.ENTRY
    if any(
        k not in held or (languages.one(v, language) != languages.one(held[k], language) if k in text else v != held[k])
        for k, v in entry.items()
    ):
        report.warning(
            "known-license",
            f"license {entry['id']} is known to tabledoc; its title, url and terms are tabledoc's, not the ones written",
            where,
        )
    return held


def _ordered(table: dict[str, Any]) -> dict[str, Any]:
    """Keys in a fixed order: depends_on, filled in last, after sql; documents, placed last, before columns."""
    order = ["schema", "name", *shape.TABLE_KEYS, "documents", "columns", "metrics", "annotations"]
    return {k: table[k] for k in order if k in table}
