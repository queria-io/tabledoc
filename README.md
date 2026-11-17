<p align="center"><img src="assets/icon.svg" width="96" alt=""></p>

# tabledoc

[日本語](README.ja.md)

tabledoc reads the description of a dataset that people write in YAML and Markdown (or in a dbt project's yml), checks it, and builds one JSON file for machines to read: `tabledoc.json`.

- One YAML file per table, next to a Markdown guide. Keys follow dbt's `models:` entries
- Semantics (join keys, dimensions, metrics) follow dbt's semantic layer
- In a dbt project, descriptions, SQL and lineage come from `target/manifest.json`
- `tabledoc.json` refers to the guides and the files they link to by path and sha256; `tabledoc push` sends what a receiver lacks

## Install

```bash
uv tool install tabledoc   # or: pip install tabledoc
```

## Use

```
tabledoc.yml              the dataset
README.md                 its overview
sales/orders.yml          the table sales.orders
sales/orders.md           its guide
```

```yaml
# tabledoc.yml
$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json
name: shop
title: Shop sales
language: en
licenses: [CC-BY-4.0]
```

```yaml
# sales/orders.yml
$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json
title: Orders
description: One row is one order.
primary_key: [order_id]
columns:
  - name: order_id
    entity: primary
  - name: ordered_at
    dimension: time
    granularity: day
metrics:
  - name: revenue
    agg: sum
    expr: amount
```

```bash
tabledoc validate            # check
tabledoc build               # check and write target/tabledoc.json
tabledoc push https://example.com/metadata   # send it, with TABLEDOC_TOKEN as the Bearer token
```

In a dbt project, run `dbt compile` first, and write `tabledoc.yml` next to `dbt_project.yml`.

## Specification

[docs/spec.md](docs/spec.md) ([日本語](docs/ja/spec.md)). The JSON Schemas are in [src/tabledoc/schemas](src/tabledoc/schemas) and served at `https://queria-io.github.io/tabledoc/schemas/`.

## License

MIT
