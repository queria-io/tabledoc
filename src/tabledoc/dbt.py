"""Tables from a dbt project's target/manifest.json.

The tables are the enabled models materialized as table, view or incremental,
under their `schema` and `alias`. A model's description comes from its yml:
`description`, the columns' `description`, the primary key from `constraints`,
`entity`, `dimension` and `granularity`, and the keys dbt does not have under
`config.meta`. `metrics` come from the semantic layer. The SQL is `compiled_code`.

`dependencies` maps the alias another dataset is attached under in the SQL to its
URL, read from the ATTACHes in profiles.yml, so `depends_on` can
name tables of other datasets.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import schemas
from .report import Report
from .source import Key, Table, sibling_guide

MATERIALIZED = ("table", "view", "incremental")
#: The keys of a table file a model writes under config.meta.
TABLE_META = (
    "title",
    "title_reading",
    "topics",
    "synonyms",
    "hidden",
    "primary_key",
    "licenses",
    "sources",
    "temporal_coverage",
    "spatial_coverage",
    "documents",
    "annotations",
)
COLUMN_META = ("title", "title_reading", "topics", "synonyms", "asset", "annotations")


def _meta(node: dict[str, Any]) -> dict[str, Any]:
    meta = (node.get("config") or {}).get("meta") or node.get("meta") or {}
    return meta if isinstance(meta, dict) else {}


def _semantic(column: dict[str, Any]) -> dict[str, Any]:
    """dbt's `entity` as the name of its code system, `dimension` as its type, and `granularity`."""
    entity, dimension = column.get("entity"), column.get("dimension")
    found = {
        "entity": entity.get("name") if isinstance(entity, dict) else None,
        "dimension": dimension.get("type") if isinstance(dimension, dict) else dimension,
        "granularity": column.get("granularity"),
    }
    return {k: v for k, v in found.items() if v}


def _column(column: dict[str, Any]) -> dict[str, Any]:
    meta = _meta(column)
    return {
        "name": column.get("name"),
        **({"description": column["description"]} if column.get("description") else {}),
        **{k: meta[k] for k in COLUMN_META if k in meta},
        **_semantic(column),
    }


def _metrics(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Each model's simple metrics, by the model's unique_id."""
    models = {
        sm.get("name"): (sm.get("depends_on") or {}).get("nodes") or []
        for sm in (manifest.get("semantic_models") or {}).values()
    }
    found: dict[str, list[dict[str, Any]]] = {}
    for metric in (manifest.get("metrics") or {}).values():
        params = metric.get("type_params") or {}
        aggregation = params.get("metric_aggregation_params") or {}
        if metric.get("type") != "simple" or not aggregation.get("semantic_model"):
            continue
        entry = {
            "name": metric.get("name"),
            **({"agg": aggregation["agg"]} if aggregation.get("agg") else {}),
            **({"expr": params["expr"]} if params.get("expr") else {}),
            **({"description": metric["description"]} if metric.get("description") else {}),
        }
        for model in models.get(aggregation["semantic_model"], []):
            found.setdefault(model, []).append(entry)
    return found


def _primary_key(node: dict[str, Any]) -> list[str] | None:
    """The columns of a `primary_key` constraint, on the model or on one column."""
    for constraint in node.get("constraints") or []:
        if isinstance(constraint, dict) and constraint.get("type") == "primary_key" and constraint.get("columns"):
            return [str(c) for c in constraint["columns"]]
    for column in (node.get("columns") or {}).values():
        for constraint in (column.get("constraints") or []) if isinstance(column, dict) else []:
            if isinstance(constraint, dict) and constraint.get("type") == "primary_key":
                return [str(column.get("name"))]
    return None


def _yml_path(root: Path, node: dict[str, Any]) -> Path:
    """The yml that describes the model, else its SQL file."""
    patch = node.get("patch_path")
    written = patch.split("://", 1)[-1] if isinstance(patch, str) else node.get("original_file_path", "")
    return root / written


def tables(manifest: dict[str, Any], root: Path, report: Report) -> list[Table]:
    """The tables dbt builds, each with its description, SQL and the guide beside its SQL."""
    metrics = _metrics(manifest)
    found = []
    for uid, node in sorted((manifest.get("nodes") or {}).items()):
        config = node.get("config") or {}
        if (
            node.get("resource_type") != "model"
            or config.get("enabled") is False
            or config.get("materialized") not in MATERIALIZED
        ):
            continue
        meta = _meta(node)
        if "docs" in meta:
            # The earlier name of `documents`, read as it (the older format).
            report.info("legacy-format", f"{node.get('name')}: config.meta.docs is read as documents; rename it", _yml_path(root, node))
            meta = {**{k: v for k, v in meta.items() if k != "docs"}, "documents": meta.get("documents", meta["docs"])}
        if "listed" in meta:
            report.info("legacy-format", f"{node.get('name')}: config.meta.listed is read as hidden; rename it", _yml_path(root, node))
            meta = {**{k: v for k, v in meta.items() if k != "listed"}, "hidden": meta.get("hidden", meta["listed"] is False)}
        if "keywords" in meta:
            report.info("legacy-format", f"{node.get('name')}: config.meta.keywords is read as topics; rename it", _yml_path(root, node))
            meta = {**{k: v for k, v in meta.items() if k != "keywords"}, "topics": meta.get("topics", meta["keywords"])}
        columns = [_column(c) for c in (node.get("columns") or {}).values() if isinstance(c, dict)]
        primary_key = _primary_key(node)
        if primary_key and "primary_key" in meta:
            report.error(
                "described-twice", f"{node.get('name')}: primary_key in config.meta and in constraints; keep one",
                _yml_path(root, node),
            )
        described = {
            **({"description": node["description"]} if node.get("description") else {}),
            **{k: meta[k] for k in TABLE_META if k in meta},
            **({"primary_key": primary_key} if primary_key and "primary_key" not in meta else {}),
            **({"columns": columns} if columns else {}),
            **({"metrics": metrics[uid]} if uid in metrics else {}),
        }
        path = _yml_path(root, node)
        schemas.check({"$schema": schemas.TABLE, **described}, schemas.TABLE, path, report)
        code = node.get("compiled_code")
        sql_file = root / node.get("original_file_path", "")
        guide = sibling_guide(root, sql_file)
        found.append(
            Table(
                str(node.get("schema", "")),
                str(node.get("alias") or node.get("name", "")),
                record={
                    **described,
                    "materialized": config["materialized"],
                    **({"sql": code.strip()} if isinstance(code, str) and code.strip() else {}),
                    **({"source_path": node["original_file_path"]} if node.get("original_file_path") else {}),
                },
                path=path,
                guide=guide,
            )
        )
    return found


_ENV_VAR = re.compile(r"""\{\{\s*env_var\(\s*(['"])(.+?)\1\s*(?:,\s*(['"])(.*?)\3\s*)?\)\s*\}\}""")


def _render(text: str, env: Mapping[str, str]) -> str | None:
    """``text`` with `{{ env_var('NAME', 'default') }}` replaced. None when a value is missing."""
    if any(m.group(2) not in env and m.group(4) is None for m in _ENV_VAR.finditer(text)):
        return None
    rendered = _ENV_VAR.sub(lambda m: env.get(m.group(2), m.group(4) or ""), text)
    return None if "{" in rendered else rendered


_CATALOG_URL = re.compile(r"(https?://.+?/)(?:versions/[^/]+/)?(?:metadata\.db|ducklake\.duckdb)")


def _url(path: str, env: Mapping[str, str]) -> str | None:
    """The URL of the dataset a DuckLake ATTACH path reads."""
    rendered = _render(path, env)
    match = _CATALOG_URL.fullmatch(rendered.removeprefix("ducklake:")) if rendered else None
    return match.group(1) if match else None


def _target(profile: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any] | None:
    name = env.get("DBT_TARGET") or _render(str(profile.get("target") or "default"), env)
    target = (profile.get("outputs") or {}).get(name)
    return target if isinstance(target, dict) else None


def dependencies(profiles: dict[str, Any], env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Alias -> URL of each other dataset the profiles attach."""
    env = os.environ if env is None else env
    return {
        str(attach["alias"]): url
        for name, profile in profiles.items()
        if name != "config"
        and isinstance(profile, dict)
        and (target := _target(profile, env)) is not None
        for attach in target.get("attach") or []
        if isinstance(attach, dict)
        and attach.get("alias")
        and (url := _url(str(attach.get("path", "")), env)) is not None
    }


def keys(found: list[Table]) -> set[Key]:
    return {t.key for t in found}
