---
title: tabledoc
sidebar:
  label: Introduction
  order: 1
description: Makes a dataset's tables readable by people and AI, from dbt's manifest and the descriptions people and AI write.
---

tabledoc makes a dataset's tables readable by people and AI. It takes what dbt already knows about the tables (descriptions, SQL and lineage from `target/manifest.json`), adds what people and AI write in YAML and Markdown (titles, column descriptions, join keys, guides), checks the result, and writes it as Markdown files or as tables in a DuckLake catalog.

- One YAML file per table, next to a Markdown guide. Keys follow dbt's `models:` entries
- Semantics (join keys, dimensions, metrics) follow dbt's semantic layer
- In a dbt project, descriptions, SQL and lineage come from `target/manifest.json`
- From Python, `tabledoc.read` returns the checked description, with the guides and the files they link to by path and sha256
- `tabledoc export --markdown <folder>` writes one Markdown file per table (columns, semantics, primary key, lineage, SQL and the guide) and one for the dataset that lists them, for AI assistants and people to read
- The same description has a second form: the tables of the schema `_tabledoc`, in third normal form, which any SQL database can hold next to the data. `tabledoc load` writes them into a DuckLake catalog, where they are versioned with the data (by [FDL](https://fdl.queria.io), say), and `tabledoc dump` writes the files back from them

## Install

```bash
uv tool install tabledoc   # or: pip install tabledoc
```

## Use

```
tabledoc.yml                  the dataset
README.md                     its overview
sales/orders.tabledoc.yml     the table sales.orders
sales/orders.md               its guide
```

```yaml
# tabledoc.yml
$schema: https://tabledoc.queria.io/schemas/dataset/v1.json
name: shop
title: Shop sales
language: en
licenses: [CC-BY-4.0]
```

```yaml
# sales/orders.tabledoc.yml
$schema: https://tabledoc.queria.io/schemas/table/v1.json
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
tabledoc export --markdown ai-docs/   # one Markdown file per table, for AI to read
```

In a dbt project, run `dbt compile` first, and write `tabledoc.yml` next to `dbt_project.yml`.

## Specification

The [specification](/spec) defines the files, the checks and what `tabledoc.read` returns. The JSON Schemas are served at `https://tabledoc.queria.io/schemas/`.
