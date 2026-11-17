from __future__ import annotations

import hashlib
import json

from tabledoc.build import Options, build, to_json
from tabledoc.report import Report, SpecError

import pytest

DATASET = "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\n"
TABLE = "$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json\n"


def run(root, **kwargs):
    report = Report()
    built = build(Options(root, with_source=False, **kwargs), report)
    return built.document, report


def codes(report):
    return sorted(f.code for f in report.findings)


def test_tables_by_place_with_guides_and_linked_files(write):
    root = write(
        {
            "tabledoc.yml": DATASET
            + "name: shop\ntitle: Shop\nlanguage: en\nissued: 2026-10-30\n"
            + "schemas: [{name: sales, guide: docs/sales.md}]\ndocs: [docs/./method.md]\n"
            + "queria: {cover: x}\nannotations: {other: {a: 1}}\n",
            "README.md": "See ![chart](docs/chart.png) and [site](https://example.com).\n",
            "docs/sales.md": "# Sales\n",
            "docs/method.md": "[back](../README.md)\n",
            "docs/chart.png": b"\x89PNG",
            "sales/orders.yml": TABLE
            + "title: Orders\nprimary_key: [id]\nqueria: {published: false}\n"
            + "columns:\n  - {name: id, entity: primary}\n  - {name: shop, entity: {type: foreign, name: shop_id}}\n"
            + "  - {name: day, dimension: time, granularity: day}\n"
            + "metrics: [{name: total, agg: sum, expr: amount}]\n",
            "sales/orders.md": "Guide.\n",
            "top.yml": TABLE + "name: things\n",
            "deep/a/b.yml": TABLE + "table: other.thing\n",
            "models/schema.yml": "version: 2\nmodels: []\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    assert document["dataset"] == {
        "name": "shop",
        "title": "Shop",
        "language": "en",
        "issued": "2026-10-30",
        "guide": "README.md",
        "docs": ["docs/method.md"],
        "annotations": {"other": {"a": 1}, "queria": {"cover": "x"}},
    }
    assert document["schemas"] == [{"name": "sales", "guide": "docs/sales.md"}]
    assert [(t["schema"], t["name"]) for t in document["tables"]] == [
        ("main", "things"),
        ("other", "thing"),
        ("sales", "orders"),
    ]
    orders = document["tables"][2]
    assert orders == {
        "schema": "sales",
        "name": "orders",
        "title": "Orders",
        "primary_key": ["id"],
        "guide": "sales/orders.md",
        "columns": [
            {"name": "id", "entity": {"type": "primary"}},
            {"name": "shop", "entity": {"type": "foreign", "name": "shop_id"}},
            {"name": "day", "dimension": {"type": "time"}, "granularity": "day"},
        ],
        "metrics": [{"name": "total", "agg": "sum", "expr": "amount"}],
        "annotations": {"queria": {"published": False}},
    }
    paths = [f["path"] for f in document["files"]]
    assert paths == ["README.md", "docs/chart.png", "docs/method.md", "docs/sales.md", "sales/orders.md"]
    png = next(f for f in document["files"] if f["path"] == "docs/chart.png")
    assert png == {
        "path": "docs/chart.png",
        "sha256": hashlib.sha256(b"\x89PNG").hexdigest(),
        "bytes": 4,
        "media_type": "image/png",
    }
    again, _ = run(root)
    assert to_json(again) == to_json(document)


def test_the_older_format(write):
    root = write(
        {
            "queria.yml": "$schema: https://queria.io/schemas/dataset/v1.json\n"
            + "name: old\ntitle: Old\nlanguage: ja\nthemes: [economy]\ncover: x\n"
            + "catalogs: {other: https://data.example/datasets/o/other/}\n",
            "models/a.md": "---\n$schema: https://queria.io/schemas/table/v1.json\ntable: s.a\n"
            + "primary_key: [id]\npublished: false\nfields:\n"
            + "  - {name: id, semantic: {role: entity, name: code}}\n"
            + "  - {name: pref, semantic: {role: entity, name: lg_code}}\n"
            + "  - {name: kind, semantic: {role: dimension}}\n"
            + "  - {name: value, semantic: {role: measure, agg: sum}}\n"
            + "  - {name: count, semantic: {role: measure}}\n"
            + "sql: select * from other.x.y join s.b using (id)\n---\n\nThe guide.\n",
            "models/b.md": "---\n$schema: https://queria.io/schemas/table/v1.json\ntable: s.b\n---\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    assert "metric-without-agg" in codes(report)
    assert document["dataset"]["annotations"] == {"queria": {"themes": ["economy"], "cover": "x"}}
    assert "catalogs" not in document["dataset"]
    a = document["tables"][0]
    assert a["columns"] == [
        {"name": "id", "entity": {"type": "primary", "name": "code"}},
        {"name": "pref", "entity": {"type": "foreign", "name": "lg_code"}},
        {"name": "kind", "dimension": {"type": "categorical"}},
        {"name": "value"},
        {"name": "count"},
    ]
    assert a["metrics"] == [
        {"name": "value", "agg": "sum", "expr": "value"},
        {"name": "count", "expr": "count"},
    ]
    assert a["depends_on"] == ["https://data.example/datasets/o/other/#x.y", "s.b"]
    assert a["guide"] == "models/a.md"
    assert a["annotations"] == {"queria": {"published": False}}
    sent = next(f for f in document["files"] if f["path"] == "models/a.md")
    assert sent["sha256"] == hashlib.sha256(b"The guide.\n").hexdigest()
    assert "guide" not in document["tables"][1]


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"x/a.yml": TABLE + "table: s.a\n", "y/a.yml": TABLE + "table: s.a\n"}, "described-twice"),
        ({"a/b/c.yml": TABLE}, "table-unplaced"),
        ({"README.md": "[x](../outside.md)\n"}, "link-outside"),
        ({"README.md": "[x](missing.md)\n"}, "link-broken"),
        ({"s/a.yml": TABLE + "columns: [{name: a, entity: wrong}]\n"}, "schema-violation"),
    ],
)
def test_findings(write, files, code):
    document, report = run(write({"tabledoc.yml": DATASET + "name: d\n", **files}))
    assert code in codes(report)


def test_missing_docs_are_errors(write):
    _, report = run(write({"tabledoc.yml": DATASET + "name: d\ndocs: [nothing.md]\n"}))
    assert codes(report) == ["file-missing"]


@pytest.mark.parametrize(
    "files",
    [
        {"tabledoc.yml": DATASET + "name: d\n", "queria.yml": "name: d\n"},
        {"tabledoc.yml": "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v9.json\nname: d\n"},
        {"tabledoc.yml": DATASET + "name: d\n", "s/a.yml": "$schema: https://queria-io.github.io/tabledoc/schemas/table/v9.json\n"},
        {},
    ],
)
def test_cannot_read(write, files):
    with pytest.raises(SpecError):
        run(write(files))


def model(name, schema="s", materialized="table", **node):
    return {
        f"model.p.{name}": {
            "resource_type": "model",
            "name": name,
            "schema": schema,
            "alias": name,
            "original_file_path": f"models/{name}.sql",
            "patch_path": "p://models/schema.yml",
            "config": {"materialized": materialized, "enabled": True, "meta": node.pop("meta", {})},
            "compiled_code": node.pop("sql", f"select 1 as id from s.base"),
            "columns": node.pop("columns", {}),
            "description": node.pop("description", ""),
        }
    }


def manifest(**nodes):
    return json.dumps({"nodes": {k: v for n in nodes.values() for k, v in n.items()}, **MANIFEST_EXTRA})


MANIFEST_EXTRA = {
    "semantic_models": {"semantic_model.p.orders": {"name": "orders", "depends_on": {"nodes": ["model.p.orders"]}}},
    "metrics": {
        "metric.p.total": {
            "name": "total",
            "type": "simple",
            "description": "Sum",
            "type_params": {"expr": "amount", "metric_aggregation_params": {"semantic_model": "orders", "agg": "sum"}},
        }
    },
}


def test_dbt_models(write):
    nodes = manifest(
        orders=model(
            "orders",
            description="One row per order",
            meta={"title": "Orders", "primary_key": ["id"], "queria": {"themes": ["x"]}},
            columns={
                "id": {"name": "id", "description": "", "meta": {}, "config": {"meta": {"title": "ID"}},
                       "entity": {"type": "primary", "name": "order", "description": "", "label": None, "config": {}},
                       "dimension": None, "granularity": None},
                "day": {"name": "day", "description": "Day", "dimension": "time", "granularity": "day"},
            },
        ),
        base=model("base", sql="select 1 as id"),
        hidden=model("hidden", materialized="ephemeral"),
        python=model("python", schema="py"),
    )
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "dbt_project.yml": "name: p\n",
            "target/manifest.json": nodes,
            "models/orders.md": "Guide\n",
            "tables/python.yml": TABLE + "table: py.python\ntitle: Made in Python\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    tables = {(t["schema"], t["name"]): t for t in document["tables"]}
    assert set(tables) == {("s", "orders"), ("s", "base"), ("py", "python")}
    assert tables[("s", "base")] == {"schema": "s", "name": "base", "sql": "select 1 as id", "depends_on": []}
    assert tables[("py", "python")]["title"] == "Made in Python"
    assert tables[("py", "python")]["sql"] == "select 1 as id from s.base"
    assert tables[("s", "orders")] == {
        "schema": "s",
        "name": "orders",
        "title": "Orders",
        "description": "One row per order",
        "primary_key": ["id"],
        "sql": "select 1 as id from s.base",
        "depends_on": ["s.base"],
        "guide": "models/orders.md",
        "columns": [
            {"name": "id", "title": "ID", "entity": {"type": "primary", "name": "order"}},
            {"name": "day", "description": "Day", "dimension": {"type": "time"}, "granularity": "day"},
        ],
        "metrics": [{"name": "total", "agg": "sum", "expr": "amount", "description": "Sum"}],
        "annotations": {"queria": {"themes": ["x"]}},
    }


def test_a_table_is_described_in_one_place(write):
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "dbt_project.yml": "name: p\n",
            "target/manifest.json": manifest(a=model("a", description="from dbt")),
            "s/a.yml": TABLE + "title: from the table file\n",
        }
    )
    _, report = run(root)
    assert codes(report) == ["described-twice"]


def test_dbt_without_a_manifest_is_a_warning(write):
    _, report = run(write({"tabledoc.yml": DATASET + "name: d\n", "dbt_project.yml": "name: p\n"}))
    assert codes(report) == ["manifest-missing"]
