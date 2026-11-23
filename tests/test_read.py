from __future__ import annotations

import hashlib
import json

import pytest

from tabledoc import Options, read
from tabledoc.report import Report, SpecError

DATASET = "$schema: https://tabledoc.queria.io/schemas/dataset/v1.json\n"
TABLE = "$schema: https://tabledoc.queria.io/schemas/table/v1.json\n"


def run(root, **kwargs):
    report = Report()
    d = read(Options(root, with_source=False, **kwargs), report)
    document = {"dataset": d.dataset, "schemas": d.schemas, "tables": d.tables, "files": [f.entry() for f in d.files]}
    return document, report


def codes(report):
    return sorted(f.code for f in report.findings)


def test_tables_by_place_with_guides_and_linked_files(write):
    root = write(
        {
            "tabledoc.yml": DATASET
            + "name: shop\ntitle: Shop\nlanguage: en\nissued: 2026-10-30\n"
            + "schemas: [{name: sales, documents: [docs/sales/README.md]}]\ndocuments: [docs/./method.md]\n"
            + "image: docs/chart.png\nsynonyms: [store]\nannotations: {other: {a: 1}}\n",
            "README.md": "See ![chart](docs/chart.png) and [site](https://example.com).\n",
            "docs/sales/README.md": "# Sales\n",
            "docs/method.md": "[back](../README.md)\n",
            "docs/chart.png": b"\x89PNG",
            "sales/orders.tabledoc.yml": TABLE
            + "title: Orders\ntitle_reading: オーダーズ\nhidden: true\nprimary_key: [id]\n"
            + "columns:\n  - {name: id}\n  - {name: shop, entity: shop_id}\n"
            + "  - {name: day, dimension: time, granularity: day}\n"
            + "metrics: [{name: total, agg: sum, expr: amount}]\n",
            "sales/orders.md": "Guide.\n",
            "things.tabledoc.yml": TABLE + "name: things\n",
            "other/thing.tabledoc.yml": TABLE,
            "models/schema.yml": "version: 2\nmodels: []\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    assert document["dataset"] == {
        "name": "shop",
        "title": {"en": "Shop"},
        "language": "en",
        "synonyms": {"en": ["store"]},
        "issued": "2026-10-30",
        "image": "docs/chart.png",
        "documents": ["README.md", "method.md"],
        "annotations": {"other": {"a": 1}},
    }
    assert document["schemas"] == [{"name": "sales", "documents": ["sales/README.md"]}]
    assert [(t["schema"], t["name"]) for t in document["tables"]] == [
        ("main", "things"),
        ("other", "thing"),
        ("sales", "orders"),
    ]
    orders = document["tables"][2]
    assert orders == {
        "schema": "sales",
        "name": "orders",
        "title": {"en": "Orders"},
        "title_reading": {"en": "オーダーズ"},
        "hidden": True,
        "primary_key": ["id"],
        "documents": ["sales/orders/README.md"],
        "columns": [
            {"name": "id"},
            {"name": "shop", "entity": "shop_id"},
            {"name": "day", "dimension": "time", "granularity": "day"},
        ],
        "metrics": [{"name": "total", "agg": "sum", "expr": "amount"}],
    }
    # Each document goes into the folder of what it is for; what they link to stays where it is.
    paths = [f["path"] for f in document["files"]]
    assert paths == ["README.md", "docs/chart.png", "method.md", "sales/README.md", "sales/orders/README.md"]
    d = read(Options(root, with_source=False), Report())
    method = next(f for f in d.files if f.path == "method.md")
    assert method.local == "docs/method.md"
    assert d.content(method) == b"[back](README.md)\n"
    assert method.sha256 == hashlib.sha256(b"[back](README.md)\n").hexdigest()
    png = next(f for f in document["files"] if f["path"] == "docs/chart.png")
    assert png == {
        "path": "docs/chart.png",
        "sha256": hashlib.sha256(b"\x89PNG").hexdigest(),
        "bytes": 4,
        "media_type": "image/png",
    }
    again, _ = run(root)
    assert json.dumps(again) == json.dumps(document)


def test_the_older_format(write):
    root = write(
        {
            "queria.yml": "$schema: https://queria.io/schemas/dataset/v1.json\n"
            + "name: old\ntitle: Old\ntitle_kana: オールド\nlanguage: ja\nthemes: [economy]\ncover: cover.png\n"
            + "keywords: [money]\n"
            + "sources: [{title: Site, path: https://site.example}]\n"
            + "catalogs: {other: https://data.example/datasets/o/other/}\n",
            "models/a.md": "---\n$schema: https://queria.io/schemas/table/v1.json\ntable: s.a\n"
            + "primary_key: [id]\npublished: false\nfields:\n"
            + "  - {name: id, semantic: {role: entity, name: code}}\n"
            + "  - {name: pref, semantic: {role: entity, name: lg_code}}\n"
            + "  - {name: kind, semantic: {role: dimension}}\n"
            + "  - {name: value, semantic: {role: measure, agg: sum}}\n"
            + "  - {name: count, semantic: {role: measure}}\n"
            + "sql: select * from other.x.y join s.b using (id)\n---\n\nThe guide.\n",
            "models/b.md": "---\n$schema: https://queria.io/schemas/table/v1.json\ntable: s.b\n"
            + "keywords: [rates]\npublished: true\n---\n",
            "cover.png": b"PNG",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    assert "metric-without-agg" in codes(report)
    assert document["dataset"]["title_reading"] == {"ja": "オールド"}
    assert document["dataset"]["image"] == "cover.png"
    assert document["dataset"]["topics"] == {"ja": ["money"]}
    assert "annotations" not in document["dataset"]
    assert document["dataset"]["sources"] == [
        {"id": "https://site.example", "title": {"ja": "Site"}, "url": {"ja": "https://site.example"}}
    ]
    assert "catalogs" not in document["dataset"]
    assert read(Options(root, with_source=False), Report()).dependencies == {
        "other": {"url": "https://data.example/datasets/o/other/"}
    }
    a = document["tables"][0]
    assert a["columns"] == [
        {"name": "id", "entity": "code"},
        {"name": "pref", "entity": "lg_code"},
        {"name": "kind", "dimension": "categorical"},
        {"name": "value"},
        {"name": "count"},
    ]
    assert a["metrics"] == [
        {"name": "value", "agg": "sum", "expr": "value"},
        {"name": "count", "expr": "count"},
    ]
    assert a["depends_on"] == ["other.x.y", "s.b"]
    assert a["documents"] == ["s/a/README.md"]
    assert a["hidden"] is True
    sent = next(f for f in document["files"] if f["path"] == "s/a/README.md")
    assert sent["sha256"] == hashlib.sha256(b"The guide.\n").hexdigest()
    assert "documents" not in document["tables"][1]
    assert document["tables"][1]["topics"] == {"ja": ["rates"]}
    assert document["tables"][1]["hidden"] is False
    d = read(Options(root, with_source=False), Report())
    assert d.content(next(f for f in d.files if f.path == "s/a/README.md")) == b"The guide.\n"


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"a/b/c.tabledoc.yml": TABLE}, "table-unplaced"),
        ({"s/a.yml": TABLE}, "table-misnamed"),
        ({"s/a.tabledoc.yml": TABLE + "name: b\n"}, "table-name"),
        ({"s/a.tabledoc.yml": TABLE + "table: s.a\n"}, "schema-violation"),
        ({"README.md": "[x](../outside.md)\n"}, "link-outside"),
        ({"README.md": "[x](missing.md)\n"}, "link-broken"),
        ({"s/a.tabledoc.yml": TABLE + "columns: [{name: a, dimension: wrong}]\n"}, "schema-violation"),
    ],
)
def test_findings(write, files, code):
    _, report = run(write({"tabledoc.yml": DATASET + "name: d\n", **files}))
    assert code in codes(report)


def test_missing_docs_are_errors(write):
    _, report = run(write({"tabledoc.yml": DATASET + "name: d\ndocuments: [nothing.md]\n"}))
    assert codes(report) == ["file-missing"]


@pytest.mark.parametrize(
    "files",
    [
        {"tabledoc.yml": DATASET + "name: d\n", "queria.yml": "name: d\n"},
        {"tabledoc.yml": "$schema: https://tabledoc.queria.io/schemas/dataset/v9.json\nname: d\n"},
        {"tabledoc.yml": DATASET + "name: d\n", "s/a.tabledoc.yml": "$schema: https://tabledoc.queria.io/schemas/table/v9.json\n"},
        {},
    ],
)
def test_cannot_read(write, files):
    with pytest.raises(SpecError):
        run(write(files))


@pytest.mark.parametrize(
    "files",
    [
        {"tabledoc.yml": "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\nname: d\n"},
        {"tabledoc.yml": DATASET + "name: d\n", "s/a.tabledoc.yml": "$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json\n"},
    ],
)
def test_moved_schema_urls_are_refused_with_the_new_one(write, files):
    with pytest.raises(SpecError, match="has moved; write https://tabledoc.queria.io/schemas/"):
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
            "compiled_code": node.pop("sql", "select 1 as id from s.base"),
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
            meta={"title": "Orders", "primary_key": ["id"], "hidden": True},
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
            "py/python.tabledoc.yml": TABLE + "title: Made in Python\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    tables = {(t["schema"], t["name"]): t for t in document["tables"]}
    assert set(tables) == {("s", "orders"), ("s", "base"), ("py", "python")}
    assert tables[("s", "base")] == {
        "schema": "s",
        "name": "base",
        "materialized": "table",
        "sql": "select 1 as id",
        "depends_on": [],
        "source_path": "models/base.sql",
    }
    assert tables[("py", "python")]["title"] == {"und": "Made in Python"}
    assert tables[("py", "python")]["sql"] == "select 1 as id from s.base"
    assert tables[("s", "orders")] == {
        "schema": "s",
        "name": "orders",
        "title": {"und": "Orders"},
        "description": {"und": "One row per order"},
        "hidden": True,
        "primary_key": ["id"],
        "materialized": "table",
        "sql": "select 1 as id from s.base",
        "depends_on": ["s.base"],
        "source_path": "models/orders.sql",
        "documents": ["s/orders/README.md"],
        "columns": [
            {"name": "id", "title": {"und": "ID"}, "entity": "order"},
            {"name": "day", "description": {"und": "Day"}, "dimension": "time", "granularity": "day"},
        ],
        "metrics": [{"name": "total", "agg": "sum", "expr": "amount", "description": {"und": "Sum"}}],
    }


def dbt_columns(**columns):
    return {name: {"name": name, **c} for name, c in columns.items()}


def test_a_table_file_beside_the_model_adds_what_dbt_does_not_say(write):
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "dbt_project.yml": "name: p\n",
            ".dbtignore": "*.tabledoc.yml\n",
            "target/manifest.json": manifest(
                a=model(
                    "a",
                    description="from dbt",
                    columns=dbt_columns(id={"description": "", "constraints": [{"type": "primary_key"}]}),
                )
            ),
            "models/a.tabledoc.yml": TABLE + "title: A\ncolumns: [{name: id, title: ID}, {name: extra, title: X}]\n",
            "models/a.md": "Guide\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    a = document["tables"][0]
    assert (a["schema"], a["name"]) == ("s", "a")
    assert a["title"] == {"und": "A"}
    assert a["description"] == {"und": "from dbt"}
    assert a["primary_key"] == ["id"]
    assert a["documents"] == ["s/a/README.md"]
    assert a["columns"] == [{"name": "id", "title": {"und": "ID"}}, {"name": "extra", "title": {"und": "X"}}]


def test_a_table_file_beside_a_python_model(write):
    python_model = model("a")
    python_model["model.p.a"]["original_file_path"] = "models/a.py"
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "dbt_project.yml": "name: p\n",
            ".dbtignore": "*.tabledoc.yml\n",
            "target/manifest.json": manifest(a=python_model),
            "models/a.py": "def model(dbt, session): ...\n",
            "models/a.tabledoc.yml": TABLE + "title: A\n",
            "models/a.md": "Guide\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    a = document["tables"][0]
    assert (a["schema"], a["name"], a["title"]) == ("s", "a", {"und": "A"})
    assert a["documents"] == ["s/a/README.md"]


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"models/a.tabledoc.yml": TABLE + "description: again\n"}, "described-twice"),
        ({"models/a.tabledoc.yml": TABLE + "columns: [{name: id, description: again}]\n"}, "described-twice"),
        ({"models/b.tabledoc.yml": TABLE, "models/b.sql": "select 1"}, "table-without-model"),
    ],
)
def test_a_key_is_written_in_one_place(write, files, code):
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "dbt_project.yml": "name: p\n",
            ".dbtignore": "*.tabledoc.yml\n",
            "target/manifest.json": manifest(
                a=model("a", description="from dbt", columns=dbt_columns(id={"description": "ID"}))
            ),
            **files,
        }
    )
    _, report = run(root)
    assert codes(report) == [code]


def test_a_dbt_project_with_table_files_ignores_them_in_dbtignore(write):
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "dbt_project.yml": "name: p\n",
            "target/manifest.json": manifest(a=model("a")),
            "models/a.tabledoc.yml": TABLE + "title: A\n",
        }
    )
    _, report = run(root)
    assert codes(report) == ["dbtignore"]


def test_dbt_without_a_manifest_is_a_warning(write):
    _, report = run(write({"tabledoc.yml": DATASET + "name: d\n", "dbt_project.yml": "name: p\n"}))
    assert codes(report) == ["manifest-missing"]


def test_documents_go_into_the_folder_of_what_they_are_for(write):
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\nschemas: [{name: sales, documents: [sales/README.md, notes/codes.md]}]\n",
            "sales/README.md": "The schema. See [codes](../notes/codes.md).\n",
            "notes/codes.md": "Codes. ![map](map.png)\n",
            "notes/map.png": b"PNG",
            "sales/orders.tabledoc.yml": TABLE + "title: Orders\ndocuments: [notes/how.md]\n",
            "sales/orders.md": "The guide.\n",
            "notes/how.md": "How.\n",
        }
    )
    d = read(Options(root, with_source=False), report := Report())
    assert not report.failed, report.render()
    assert d.schemas == [{"name": "sales", "documents": ["sales/README.md", "sales/codes.md"]}]
    assert d.tables[0]["documents"] == ["sales/orders/README.md", "sales/orders/how.md"]
    assert [f.path for f in d.files] == [
        "notes/map.png",
        "sales/README.md",
        "sales/codes.md",
        "sales/orders/README.md",
        "sales/orders/how.md",
    ]
    by_path = {f.path: f for f in d.files}
    assert d.content(by_path["sales/README.md"]) == b"The schema. See [codes](codes.md).\n"
    assert d.content(by_path["sales/codes.md"]) == b"Codes. ![map](../notes/map.png)\n"


def test_two_files_at_one_path_is_an_error(write):
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\ndocuments: [a/x.md, b/x.md]\n",
            "a/x.md": "A\n",
            "b/x.md": "B\n",
        }
    )
    _, report = run(root)
    assert codes(report) == ["file-clash"]


def test_one_file_for_two_paths_is_an_error(write):
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "s/a.tabledoc.yml": TABLE + "title: A\ndocuments: [docs/method.md]\n",
            "s/b.tabledoc.yml": TABLE + "title: B\ndocuments: [docs/method.md]\n",
            "docs/method.md": "Method.\n",
        }
    )
    _, report = run(root)
    assert codes(report) == ["file-named-twice"]


def test_text_in_more_than_one_language(write):
    root = write(
        {
            "tabledoc.yml": DATASET
            + "name: shop\nlanguage: ja\ntitle: {ja: 店, en: Shop}\ndescription: 店の注文\n"
            + "topics: {ja: [小売], en: [retail]}\nsources: [{id: s, title: {ja: 出典, en: Source}, url: https://x.example}]\n",
            "sales/orders.tabledoc.yml": TABLE + "columns: [{name: id, title: {en: Order ID}}]\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    dataset = document["dataset"]
    assert dataset["title"] == {"ja": "店", "en": "Shop"}
    assert dataset["description"] == {"ja": "店の注文"}
    assert dataset["topics"] == {"ja": ["小売"], "en": ["retail"]}
    assert dataset["sources"] == [{"id": "s", "title": {"ja": "出典", "en": "Source"}, "url": {"ja": "https://x.example"}}]
    assert document["tables"][0]["columns"] == [{"name": "id", "title": {"en": "Order ID"}}]


def test_a_language_tag_is_checked(write):
    root = write({"tabledoc.yml": DATASET + "name: shop\ntitle: {'not a tag': x}\n"})
    _, report = run(root)
    assert [f.code for f in report.findings] == ["schema-violation"]


def test_a_map_with_no_text_is_an_error(write):
    root = write({"tabledoc.yml": DATASET + "name: shop\ntitle: {ja: ''}\ntopics: {ja: []}\n"})
    _, report = run(root)
    assert [f.code for f in report.findings] == ["schema-violation", "schema-violation"]


def test_an_empty_title_is_an_error(write):
    root = write({"tabledoc.yml": DATASET + "name: shop\ntitle: ''\n"})
    _, report = run(root)
    assert [f.code for f in report.findings] == ["schema-violation"]


def test_a_readme_no_longer_found_by_itself_is_a_warning(write):
    root = write(
        {
            "tabledoc.yml": DATASET + "name: d\n",
            "sales/README.md": "The schema.\n",
            "sales/orders.tabledoc.yml": TABLE,
            "sales/orders/README.md": "The guide.\n",
        }
    )
    _, report = run(root)
    assert codes(report) == ["unlisted-readme", "unlisted-readme"]


def test_a_cover_that_is_not_a_path_is_not_an_image(write):
    root = write(
        {
            "queria.yml": "$schema: https://queria.io/schemas/dataset/v1.json\n"
            + "name: old\ntitle: Old\nlanguage: ja\ncover: 🏦\n",
        }
    )
    document, report = run(root)
    assert not report.failed, report.render()
    assert "image" not in document["dataset"]


def test_a_source_without_an_id_is_a_finding_not_a_crash(write):
    root = write({"tabledoc.yml": DATASET + "name: d\ntitle: D\nsources: [{title: Site, url: https://site.example}]\n"})
    _, report = run(root)
    assert report.failed
