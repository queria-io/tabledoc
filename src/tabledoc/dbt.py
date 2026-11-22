"""Tables from a dbt project's target/manifest.json.

The tables are the enabled models materialized as table, view or incremental,
under their `schema` and `alias`. A model's description comes from its yml:
`description`, the columns' `description`, `entity`, `dimension` and
`granularity`, and the keys dbt does not have under `config.meta`. `metrics`
come from the semantic layer. The SQL is `compiled_code`.

`catalogs` maps the alias another dataset is attached under in the SQL to its
repository URL, read from the ATTACHes in profiles.yml, so `depends_on` can
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
    "keywords",
    "primary_key",
    "licenses",
    "sources",
    "temporal_coverage",
    "spatial_coverage",
    "docs",
    "queria",
    "annotations",
)
COLUMN_META = ("title", "asset", "annotations")


def _meta(node: dict[str, Any]) -> dict[str, Any]:
    meta = (node.get("config") or {}).get("meta") or node.get("meta") or {}
    return meta if isinstance(meta, dict) else {}


def _typed(value: Any) -> Any:
    """dbt's entity or dimension as a table file writes it: its type, or {type, name}."""
    if isinstance(value, dict):
        return {k: value[k] for k in ("type", "name") if value.get(k)}
    return value or None


def _column(column: dict[str, Any]) -> dict[str, Any]:
    meta = _meta(column)
    semantic = {k: v for k in ("entity", "dimension") if (v := _typed(column.get(k))) is not None}
    return {
        "name": column.get("name"),
        **({"description": column["description"]} if column.get("description") else {}),
        **{k: meta[k] for k in COLUMN_META if k in meta},
        **semantic,
        **({"granularity": column["granularity"]} if column.get("granularity") else {}),
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
        columns = [_column(c) for c in (node.get("columns") or {}).values() if isinstance(c, dict)]
        described = {
            **({"description": node["description"]} if node.get("description") else {}),
            **{k: meta[k] for k in TABLE_META if k in meta},
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


def _repository(path: str, env: Mapping[str, str]) -> str | None:
    """The repository URL a DuckLake ATTACH path reads."""
    rendered = _render(path, env)
    match = _CATALOG_URL.fullmatch(rendered.removeprefix("ducklake:")) if rendered else None
    return match.group(1) if match else None


def _target(profile: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any] | None:
    name = env.get("DBT_TARGET") or _render(str(profile.get("target") or "default"), env)
    target = (profile.get("outputs") or {}).get(name)
    return target if isinstance(target, dict) else None


def catalogs(profiles: dict[str, Any], env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Alias -> repository URL of each other dataset the profiles attach."""
    env = os.environ if env is None else env
    return {
        str(attach["alias"]): repository
        for name, profile in profiles.items()
        if name != "config"
        and isinstance(profile, dict)
        and (target := _target(profile, env)) is not None
        for attach in target.get("attach") or []
        if isinstance(attach, dict)
        and attach.get("alias")
        and (repository := _repository(str(attach.get("path", "")), env)) is not None
    }


def keys(found: list[Table]) -> set[Key]:
    return {t.key for t in found}
