---
title: Specification (v1)
sidebar:
  label: Specification
  order: 2
description: The files tabledoc reads, how it checks them, and the tabledoc.json it builds.
---

tabledoc reads the description of a dataset that people write (YAML and Markdown, or a dbt project's yml) and builds one JSON file for machines to read: `tabledoc.json`. It depends on no particular data store or host.

`tabledoc.json` is to the description what dbt's `manifest.json` is to a project: people do not edit it. The files the author writes are the source.

## Commands

- `tabledoc validate`: check the author's files
- `tabledoc build`: check them and write `target/tabledoc.json`
- `tabledoc push <URL>`: send `target/tabledoc.json` and the files it lists to a receiver ([push](#push))

`validate` and `build` exit with 1 when there are errors (with `--strict`, warnings too) and 2 when the files cannot be read at all.

## Files

Paths are relative to the folder that holds `tabledoc.yml` (the root).

```
tabledoc.yml              the dataset (the name is fixed)
README.md                 the dataset's overview (optional)
<schema>/<table>.yml      a table
<schema>/<table>.md       the table's guide (optional)
```

In a dbt project, tables are described in dbt's yml and each guide is a `.md` with the same name next to the model's `.sql` ([dbt projects](#dbt-projects)).

Folders whose name starts with `.`, and `target/`, `dbt_packages/`, `node_modules/` and `.venv/`, are not read.

## tabledoc.yml

The description of one dataset.

```yaml
$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json
name: boj
title: Bank of Japan time-series statistics
description: Every statistic on the Bank of Japan's time-series data search site.
language: en
keywords: [Bank of Japan, interest rates, prices]
homepage: https://github.com/queria-io/dataset-boj
update_frequency: irregular
licenses:
  - id: boj-copyright
    title: Bank of Japan copyright and disclaimer
    url: https://www.boj.or.jp/en/about/copyright.htm
sources:
  - title: Bank of Japan time-series data search site
    path: https://www.stat-search.boj.or.jp/
contributors:
  - title: Bank of Japan
    path: https://www.boj.or.jp/
    roles: [rightsHolder]
spatial_coverage: [JP]
schemas:
  - name: timeseries
    title: Time series
docs:
  - docs/methodology.md
queria:
  themes: [economy]
```

| Key | Required | Meaning |
| --- | --- | --- |
| `$schema` | yes | The format and its version |
| `name` | yes | The dataset's name: `^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$` |
| `title`, `description`, `keywords`, `homepage`, `language`, `issued`, `update_frequency` | | `language` is a BCP 47 tag; `issued` is `YYYY-MM-DD` |
| `licenses`, `sources`, `contributors`, `temporal_coverage`, `spatial_coverage` | | Written in a table file, the value is that table's alone |
| `schemas` | | `name`, `title`, `description`, `guide` (the path of the schema's guide) |
| `docs` | | Paths of documents that belong to no one table, in the order they are shown |
| `queria` | | Keys only Queria reads ([keys for one reader](#keys-for-one-reader)) |
| `annotations` | | Keys for other readers, by the reader's name |

## Table files

The description of one table. A table file is a YAML file whose `$schema` is `https://queria-io.github.io/tabledoc/schemas/table/v1.json`; YAML files without it (dbt's `schema.yml`, say) are not read. The keys follow one entry of dbt's `models:`; keys dbt does not have (`title`, `primary_key`, `sources` and so on) sit at the same level.

```yaml
$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json
name: series
title: Series
description: |-
  Every series of every database on the search site. One row is one series.
primary_key: [db, series_code]
sources:
  - path: https://www.stat-search.boj.or.jp/
columns:
  - name: db
    title: Database
    description: The same as db in databases
    dimension: categorical
  - name: series_code
    title: Series code
  - name: last_update
    title: Last updated
    dimension: time
    granularity: day
```

| Key | Meaning |
| --- | --- |
| `name` | The table's name. Defaults to the file name |
| `table` | `<schema>.<table>`. Wins over the file's place ([which table](#which-table)) |
| `title`, `description`, `keywords` | |
| `primary_key` | The columns that identify a row |
| `licenses`, `sources`, `temporal_coverage`, `spatial_coverage` | Only when they differ from the dataset's |
| `sql`, `depends_on` | For a table dbt does not build: the SQL it is made from and the tables it reads |
| `columns` | `name`, `title`, `description`, `asset`, and the semantic keys `entity`, `dimension`, `granularity` |
| `metrics` | How the table is aggregated ([semantics](#semantics)) |
| `queria`, `annotations` | Keys for one reader |

Types, nullability and row counts are not written. The data store holds the structure.

`asset: true` says the column's value is the path of a file that belongs to the row.

## Which table

- By default the place decides: a table file at `<schema>/<table>.yml` describes `<schema>.<table>`. A file directly under the root is in the `main` schema
- `table: <schema>.<table>` wins over the place. A table file at any other depth has to say it
- Two files describing the same table is an error
- dbt does not read a table file inside `models/`: dbt ignores keys outside `models:`

## Guides and documents

- A table's guide is the `.md` with the same name in the same folder as its table file (`series.md` for `series.yml`). It has no front matter
- The dataset's overview is `README.md` at the root. A schema's guide is `schemas[].guide`; other documents are listed in `docs`
- The files a Markdown document links to with a relative path (images, PDFs, other documents) are sent too. A link that leaves the root is an error; a link to a missing file is a warning; a link to a folder is left alone
- Build and maintenance notes belong in `CONTRIBUTING.md`, not in `docs`

## dbt projects

When the root has `dbt_project.yml`, tabledoc reads `target/manifest.json` (`--manifest` changes it). Run `dbt compile` (or a build) first; without a manifest, tabledoc warns and reads only the table files.

- The tables are the enabled models materialized as `table`, `view` or `incremental`, under the model's `schema` and `alias`. Ephemeral and disabled models, seeds, snapshots and tests make no table, so they are not listed. A model with no description is listed with its `sql` and `depends_on` only
- The description comes from the model's yml. `description` and the columns' `description` as they are; keys dbt does not have (`title`, `primary_key`, `sources`, a column's `title`, `asset` and so on) and `queria` under `config.meta`
- Semantics come from the columns' `entity`, `dimension` and `granularity`, and from the semantic layer's simple `metrics`
- `sql` is `compiled_code`. `depends_on` is read from it by DuckDB's parser. A table of another dataset is written `<repository URL>#<schema>.<table>`, where the URL comes from the DuckLake ATTACHes in `profiles.yml` (`--profiles`, else `DBT_PROFILES_DIR`, else the root)
- A guide is the `.md` with the same name next to the model's `.sql` (dbt ignores `.md` files without a docs block)
- A table is described in one place. When both a table file and dbt's yml describe it, that is an error. When dbt's yml says nothing about it, the table file is read, and `sql` comes from dbt

```yaml
models:
  - name: series
    description: One row is one series.
    config:
      meta:
        title: Series
        primary_key: [db, series_code]
    columns:
      - name: db
        description: The same as db in databases
        dimension: categorical
        config:
          meta: {title: Database}
```

A table dbt does not build (one made in Python, say) is described with a table file, in the same project.

## Semantics

What a column means follows dbt's semantic layer as written from dbt-core 1.12 (on the columns). These are tabledoc's own keys, not one reader's.

| Key | Value | Meaning |
| --- | --- | --- |
| `entity` | `{type, name}`, or the type alone | A join key. `type` is `primary`, `unique`, `foreign` or `natural`. `name` is the vocabulary the values come from (`corporate_number`, `lg_code`) |
| `dimension` | `categorical` or `time`, or `{type, name}` | A column to filter and group by |
| `granularity` | `day`, `month`, `year`, ... | How fine a `dimension: time` column is |
| `metrics` (table) | `[{name, agg, expr, description}]` | How to aggregate. `agg` is `sum`, `max`, `count_distinct`, ... |

In dbt, `metrics` need the semantic layer (`semantic_model: true` and a time spine). A project that does not use it can still write `entity` and `dimension` on columns.

## Keys for one reader

Keys only one reader uses are written under that reader's name. tabledoc does not check them and copies them to `annotations.<reader>` in `tabledoc.json`.

- Queria's keys are written under `queria:`, the one reader tabledoc knows by name. Queria checks them
- Other readers' keys go under `annotations: {<reader>: {...}}`

## tabledoc.json

What `tabledoc build` writes. The author's files in one document, with the older formats read as today's.

```json
{
  "$schema": "https://queria-io.github.io/tabledoc/schemas/tabledoc/v1.json",
  "generator": "tabledoc 0.1.0",
  "source": {
    "repository": "https://github.com/queria-io/dataset-boj",
    "commit": "4e07e0e…",
    "path": "",
    "dirty": false
  },
  "dataset": {
    "name": "boj",
    "title": "Bank of Japan time-series statistics",
    "licenses": [{ "id": "boj-copyright", "url": "https://www.boj.or.jp/en/about/copyright.htm" }],
    "guide": "README.md",
    "docs": ["docs/methodology.md"],
    "annotations": { "queria": { "themes": ["economy"] } }
  },
  "schemas": [{ "name": "timeseries", "title": "Time series" }],
  "tables": [
    {
      "schema": "timeseries",
      "name": "series",
      "title": "Series",
      "primary_key": ["db", "series_code"],
      "sql": "SELECT …",
      "depends_on": ["timeseries.databases"],
      "guide": "models/timeseries/mart/series.md",
      "columns": [{ "name": "db", "title": "Database", "dimension": { "type": "categorical" } }]
    }
  ],
  "files": [
    { "path": "README.md", "sha256": "…", "bytes": 1234, "media_type": "text/markdown" },
    { "path": "models/timeseries/mart/series.md", "sha256": "…", "bytes": 2345, "media_type": "text/markdown" }
  ]
}
```

- `source` is the Git working copy: `repository` is the `origin` remote as an https URL (without credentials or `.git`), `commit` is HEAD, `path` goes from the repository's root to the folder of `tabledoc.yml`, and `dirty` says whether there were changes not committed. Outside Git it is left out. A receiver leaves `source` and `generator` out when it compares two documents
- Documents are referred to by path, not included. `files` lists every file whose content is sent (guides, README, `docs`, and what they link to) with its sha256, size and media type. `guide`, `docs` and `schemas[].guide` are paths in `files`
- Semantics always come out as `{type, name}` (`dimension: categorical` is `{"type": "categorical"}`)
- Tables are sorted by `schema`, then `name`. The same input gives the same bytes
- The structure (types, nullability, row counts, whether a table is a view) is not in it

## push

`tabledoc push <URL>` sends `target/tabledoc.json` (`--file` changes it) with `Authorization: Bearer <token>`, the token from `--token` or `TABLEDOC_TOKEN`.

```
PUT <URL>                               tabledoc.json (Content-Encoding: gzip)
  ← 409 {"missing": ["<sha256>", …]}    the receiver lacks these files
PUT <URL without query>/files/<sha256>  each file's content, Content-Type its media type
PUT <URL>                               again: 201 for a new revision, 200 for the same content
```

The URL may carry a query (such as `?version=`); it is sent with the document only. Before sending, tabledoc checks that each file still has the sha256 in `tabledoc.json`.

## The older format

So that every dataset need not be rewritten at once, tabledoc also reads the format it replaces. Only tabledoc's format is written anew.

- Without `tabledoc.yml`, `queria.yml` (`https://queria.io/schemas/dataset/v1.json`) is read as `tabledoc.yml`. Its top-level `title_kana`, `themes`, `cover` and `ai_context` are read as if under `queria:`. `catalogs` is used for `depends_on` and left out of `tabledoc.json`
- Markdown whose front matter has `$schema: https://queria.io/schemas/table/v1.json` is read as a table file (the front matter) and its guide (the text below). `table:` says which table, `fields` is `columns`, and `published`, `themes` and `ai_context` are read as if under `queria:`. The guide is that Markdown's path, and what is sent is the text without the front matter
- A field's `semantic: {role, name, agg}` is read as: `role: entity` → `entity: {type: foreign, name}`, or `type: primary` when the column alone is the `primary_key`; `role: dimension` → `dimension: categorical`; `role: measure` → a metric `{name: <column>, agg, expr: <column>}` on the table (without `agg`, a warning)
- `tabledoc.yml` and `queria.yml` in the same folder is an error

## $schema and versions

- tabledoc ships its JSON Schemas and serves them at `https://queria-io.github.io/tabledoc/schemas/<kind>/v<n>.json`. The kinds are `dataset`, `table` and `tabledoc` (the built JSON)
- Adding keys keeps the version. Changing what a key means, or removing one, makes `v2`, and tabledoc reads both for a while
- A file with a `$schema` this tabledoc does not know is refused, with a request to upgrade tabledoc
- A receiver reads `tabledoc.json` by its `$schema`
