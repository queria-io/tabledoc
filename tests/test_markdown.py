from __future__ import annotations

from tabledoc import Options, read
from tabledoc.cli import main
from tabledoc.markdown import render
from tabledoc.report import Report

DATASET = "$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json\n"
TABLE = "$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json\n"

FILES = {
    "tabledoc.yml": DATASET
    + "name: shop\ntitle: Shop\nlanguage: en\nlicenses: [{id: CC-BY-4.0, url: https://example.com/by}]\n"
    + "schemas: [{name: sales, title: Sales, description: What was sold.}]\n"
    + "queria: {title_kana: ショップ}\n",
    "README.md": "# Shop\n\nSee ![chart](docs/chart.png).\n",
    "docs/chart.png": b"\x89PNG",
    "sales/orders.yml": TABLE
    + "title: Orders\ndescription: |-\n  One row is one order.\n\n  More.\nprimary_key: [id]\n"
    + "columns:\n  - {name: id, title: ID, entity: primary}\n"
    + "  - {name: shop, description: 'a | b', entity: {type: foreign, name: shop_id}}\n"
    + "  - {name: day, dimension: time, granularity: day}\n"
    + "  - {name: receipt, asset: true}\n"
    + "metrics: [{name: total, agg: sum, expr: amount}]\n",
    "sales/orders.md": "How to read it. ![chart](../docs/chart.png)\n",
    "sales/daily.yml": TABLE + "title: Daily\nsql: select day, count(*) from sales.orders group by day\n",
}


def rendered(write):
    report = Report()
    d = read(Options(write(FILES), with_source=False), report)
    assert not report.failed, report.render()
    return {path: content.decode(errors="replace") for path, content in render(d).items()}


def test_one_file_per_dataset_schema_and_table_at_the_paths_in_the_dataset(write):
    assert sorted(rendered(write)) == [
        "README.md",
        "docs/chart.png",
        "sales/README.md",
        "sales/daily/README.md",
        "sales/orders/README.md",
    ]


def test_dataset_lists_its_tables_then_its_overview(write):
    readme = rendered(write)["README.md"]
    assert readme.startswith("# Shop (`shop`)\n\n- Name: `shop`\n- Language: en\n")
    assert "- Licenses: [CC-BY-4.0](https://example.com/by)\n" in readme
    assert "### [Sales (`sales`)](sales/README.md)\n\nWhat was sold.\n" in readme
    assert "- [`sales.orders`](sales/orders/README.md) Orders: One row is one order.\n" in readme
    assert readme.endswith("---\n\n# Shop\n\nSee ![chart](docs/chart.png).\n")
    assert "ショップ" not in readme


def test_table_has_columns_semantics_lineage_and_its_guide(write):
    pages = rendered(write)
    orders = pages["sales/orders/README.md"]
    assert orders.startswith("# Orders (`sales.orders`)\n\nOne row is one order.\n\nMore.\n\n- Primary key: `id`\n")
    assert "| `id` | ID |  | entity: primary |" in orders
    assert "| `shop` |  | a \\| b | entity: foreign (shop_id) |" in orders
    assert "| `day` |  |  | dimension: time; granularity: day |" in orders
    assert "| `receipt` |  |  | asset: a file of the row |" in orders
    assert "| `total` | sum | `amount` |  |" in orders
    assert "## Read by\n\n- [`sales.daily`](../daily/README.md)\n" in orders
    # The guide's link was rewritten for its path in the dataset, so it still reaches the image.
    assert orders.endswith("---\n\nHow to read it. ![chart](../../docs/chart.png)\n")
    daily = pages["sales/daily/README.md"]
    assert "## Reads\n\n- [`sales.orders`](../orders/README.md)\n" in daily
    assert "## SQL\n\n```sql\nselect day, count(*) from sales.orders group by day\n```\n" in daily


def test_export_refuses_to_replace_files_unless_forced(write, tmp_path):
    root = write(FILES)
    out = tmp_path / "md"
    assert main(["export", "--root", str(root), "--markdown", str(out)]) == 0
    assert (out / "sales" / "orders" / "README.md").is_file()
    assert main(["export", "--root", str(root), "--markdown", str(out)]) == 2
    assert main(["export", "--root", str(root), "--markdown", str(out), "--force"]) == 0


def test_export_inside_the_root_is_not_read_again(write):
    root = write({**FILES, "sales/orders.md": "See [the table file](orders.yml).\n"})
    out = root / "ai-docs"
    assert main(["export", "--root", str(root), "--markdown", str(out)]) == 0
    assert (out / "sales" / "orders.yml").is_file()
    assert (out / ".tabledoc-export").is_file()
    assert main(["validate", "--root", str(root)]) == 0


def test_export_into_a_file_is_refused(write, tmp_path):
    root = write(FILES)
    out = tmp_path / "md"
    out.write_text("", encoding="utf-8")
    assert main(["export", "--root", str(root), "--markdown", str(out)]) == 2


def test_links_with_spaces_and_the_repository(write):
    files = {
        **FILES,
        "tabledoc.yml": FILES["tabledoc.yml"] + "repository: https://example.com/repo\ndocs: ['docs/Data dictionary.md']\n",
        "docs/Data dictionary.md": "# Dictionary\n",
    }
    report = Report()
    d = read(Options(write(files), with_source=False), report)
    assert not report.failed, report.render()
    readme = render(d)["README.md"].decode()
    assert "- Repository: https://example.com/repo\n" in readme
    assert "- [Data dictionary.md](<Data dictionary.md>)\n" in readme
