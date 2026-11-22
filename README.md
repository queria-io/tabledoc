<p align="center"><img src="public/icon.svg" width="96" alt=""></p>

# tabledoc

[日本語](README.ja.md)

tabledoc reads the description of a dataset that people write in YAML and Markdown (or in a dbt project's yml), checks it, and reads it for other programs.

- One YAML file per table, next to a Markdown guide. Keys follow dbt's `models:` entries
- Semantics (join keys, dimensions, metrics) follow dbt's semantic layer
- In a dbt project, descriptions, SQL and lineage come from `target/manifest.json`
- From Python, `tabledoc.read` returns the checked description, with the guides and the files they link to by path and sha256
- `tabledoc load` writes the description into a DuckLake catalog as ordinary tables of one schema (`_tabledoc` by default), so it travels with the data and is versioned with it by [FDL](https://fdl.queria.io). `tabledoc dump` writes the files back from it

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
tabledoc load --ducklake work.sqlite   # check, then write it into the catalog's _tabledoc schema
tabledoc dump --ducklake work.sqlite --out description/   # the files again, from the catalog
```

In a dbt project, run `dbt compile` first, and write `tabledoc.yml` next to `dbt_project.yml`.

## Specification

The documentation and the specification are at [tabledoc.queria.io](https://tabledoc.queria.io) (source: [docs/spec.md](docs/spec.md)). The JSON Schemas are in [src/tabledoc/schemas](src/tabledoc/schemas) and served at `https://queria-io.github.io/tabledoc/schemas/`.

## License

MIT
