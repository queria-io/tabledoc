---
title: Specification (v1)
sidebar:
  label: Specification
  order: 2
description: The files tabledoc reads, how it checks them, and what it returns to a program.
---

tabledoc defines how people write the description of a dataset (YAML and Markdown, or a dbt project's yml), checks it, and reads it for other programs. It depends on no particular host; `tabledoc load` writes the description into a DuckLake catalog as the tables of the [`_fdl` schema](https://fdl.queria.io/spec/fdl-schema) FDL defines, and `tabledoc dump` writes the files back from it. The files the author writes are the source.

## Commands

- `tabledoc validate`: check the author's files
- `tabledoc load`: check them and write the description into a DuckLake catalog ([Writing into a DuckLake catalog](#writing-into-a-ducklake-catalog))
- `tabledoc dump`: write the files of the description a catalog holds ([Writing the files from a catalog](#writing-the-files-from-a-catalog))

It exits with 1 when there are errors (with `--strict`, warnings too) and 2 when the files or the catalog cannot be read or written at all.

## Files

Paths are relative to the folder that holds `tabledoc.yml` (the root).

```
tabledoc.yml              the dataset (the name is fixed)
README.md                 the dataset's overview (optional)
<schema>/<table>.yml      a table
<schema>/<table>.md       the table's guide (optional; or <schema>/<table>/README.md)
<schema>/README.md        the schema's guide (optional)
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
| `schemas` | | `name`, `title`, `description`, `guide` (the path of the schema's guide; default `<name>/README.md` when it is there), `docs` (the schema's other documents) |
| `docs` | | Paths of the dataset's other documents |
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
| `docs` | Paths of the table's other documents |
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

- A table's guide is the `.md` with the same name in the same folder as its table file (`series.md` for `series.yml`), or `README.md` in the folder of that name (`series/README.md`). It has no front matter
- The dataset's overview is `README.md` at the root. A schema's guide is `schemas[].guide`, else `<schema>/README.md`
- Other documents are listed in `docs`: the dataset's in `tabledoc.yml`, a schema's in `schemas[].docs`, a table's in its table file. Paths are relative to the root
- The files a Markdown document links to with a relative path (images, PDFs, other documents) are sent too. A link that leaves the root is an error; a link to a missing file is a warning; a link to a folder is left alone
- Build and maintenance notes belong in `CONTRIBUTING.md`, not in `docs`

### Paths in the dataset

In the dataset, each folder is one thing described: the root is the dataset, `<schema>/` a schema, `<schema>/<table>/` a table. The folder's `README.md` describes it, and its other Markdown files are its documents. tabledoc places the files there, wherever the author keeps them:

| Written | Path in the dataset |
| --- | --- |
| `README.md` | `README.md` |
| an entry of `docs` | `<file name>` |
| a schema's guide | `<schema>/README.md` |
| an entry of `schemas[].docs` | `<schema>/<file name>` |
| a table's guide | `<schema>/<table>/README.md` |
| an entry of a table's `docs` | `<schema>/<table>/<file name>` |
| a file a document links to | its path under the root |

- In a Markdown document, each relative link to a file that was placed elsewhere is rewritten to point at its new path. The `sha256` and `bytes` are those of the rewritten document
- Two files at the same path in the dataset is an error

## dbt projects

When the root has `dbt_project.yml`, tabledoc reads `target/manifest.json` (`--manifest` changes it). Run `dbt compile` (or a build) first; without a manifest, tabledoc warns and reads only the table files.

- The tables are the enabled models materialized as `table`, `view` or `incremental`, under the model's `schema` and `alias`. Ephemeral and disabled models, seeds, snapshots and tests make no table, so they are not listed. A model with no description is listed with what dbt fills in only (`materialized`, `sql`, `depends_on`, `source_path`)
- The description comes from the model's yml. `description` and the columns' `description` as they are; keys dbt does not have (`title`, `primary_key`, `sources`, a column's `title`, `asset` and so on) and `queria` under `config.meta`
- Semantics come from the columns' `entity`, `dimension` and `granularity`, and from the semantic layer's simple `metrics`
- `materialized` is the model's materialization, `source_path` its `original_file_path`, and `sql` its `compiled_code`. `depends_on` is read from it by DuckDB's parser. A table of another dataset is written `<repository URL>#<schema>.<table>`, where the URL comes from the DuckLake ATTACHes in `profiles.yml` (`--profiles`, else `DBT_PROFILES_DIR`, else the root)
- A guide is the `.md` with the same name next to the model's `.sql`, or `README.md` in the folder of that name (dbt ignores `.md` files without a docs block). Other documents are `docs` under `config.meta`
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

Keys only one reader uses are written under that reader's name. tabledoc does not check them and returns them under `annotations.<reader>`.

- Queria's keys are written under `queria:`, the one reader tabledoc knows by name. Queria checks them
- Other readers' keys go under `annotations: {<reader>: {...}}`

## Reading from Python

Programs that send the description somewhere, or turn it into another format, read it with `tabledoc.read`. It checks the files as `validate` does and returns the description with the older formats read as today's.

```python
import tabledoc

report = tabledoc.Report()
d = tabledoc.read(tabledoc.Options(root), report)  # root: the folder of tabledoc.yml
if report.failed:
    print(report.render())
d.dataset   # {"name": "boj", "title": …, "guide": "README.md", "docs": ["methodology.md"], "annotations": {…}}
d.schemas   # [{"name": "timeseries", "title": "Time series"}]
d.tables    # [{"schema": "timeseries", "name": "series", "sql": …, "depends_on": […], "guide": …, "columns": […]}]
d.files     # [File(path="README.md", sha256="…", bytes=1234, media_type="text/markdown", local="README.md"), …]
d.source    # {"repository": "https://github.com/…", "commit": "…", "path": "", "dirty": False}
d.catalogs  # {"other": "https://…"}: the other datasets the SQL reads, by the name it reads them under
d.content(d.files[0])  # the bytes of that file
```

- `source` is the Git working copy: `repository` is the `origin` remote as an https URL (without credentials or `.git`), `commit` is HEAD, `path` goes from the repository's root to the folder of `tabledoc.yml`, and `dirty` says whether there were changes not committed. It is None outside Git, or with `Options(with_source=False)`
- Documents are referred to by their [paths in the dataset](#paths-in-the-dataset). `files` lists every file whose content is meant to go with the description (guides, README, `docs`, and what they link to) with that path, its sha256, size and media type, and `local`, its path under the root. `guide`, `docs`, `schemas[].guide` and `schemas[].docs` are paths in `files`. `content` gives what goes into the dataset for a file: its bytes, a Markdown document with its links rewritten, and for an older-format Markdown table file, the text without its front matter
- Semantics always come out as `{type, name}` (`dimension: categorical` is `{"type": "categorical"}`)
- Tables are sorted by `schema`, then `name`, and keys come in a fixed order. The same files give the same records
- The structure (types, nullability, row counts, whether a table is a view) is not in it

## Writing into a DuckLake catalog

`tabledoc load` checks the description as `validate` does, then writes it into a [DuckLake](https://ducklake.select) catalog as the tables of the [`_fdl` schema](https://fdl.queria.io/spec/fdl-schema). FDL defines those tables; any program that reads the catalog reads the description with it, with SQL.

```bash
tabledoc load --ducklake work.sqlite --data-path data/ --out build/assets
fdl commit work.sqlite -m "..." --assets build/assets
```

- `--ducklake`: the catalog (default: `FDL_WORKING`). `--data-path`: where new data files go (default: `FDL_DATA_PATH`, else the folder `fdl clone` noted beside the catalog)
- `--out`: also write the folder `fdl commit --assets` takes: each file of `_fdl.files` under `files/<path>`. With `--assets <folder>`, the files below it (those of the build's asset columns) are linked under `data/`. The folder has to be empty or written by an earlier `load`, and outside `.fdl/`, which only fdl writes
- `--unlisted`: the catalog's tables and views that have no description get a row in `_fdl.tables` with `profile` false, and the attribute `queria-published` false
- A described table or column, or a primary key column, that is not in the catalog is an error, and so is an `asset` column that is not `varchar`. Names match without regard to case, as in DuckDB
- `issued` other than `YYYY-MM-DD` is an error
- On an error (with `--strict`, a warning) nothing is written

| Table | From |
| --- | --- |
| `_fdl.dataset` | `tabledoc.yml`: `title`, `description`, `language`, `keywords`, `homepage`, `issued`, `update_frequency`, `licenses`, `sources`, `contributors`, `temporal_coverage`, `spatial_coverage` |
| `_fdl.schemas` | `schemas[]` with a `title` or a `description` |
| `_fdl.tables` | each table and view described: `title`, `description`, `keywords`, `licenses`, `sources`, `temporal_coverage`, `spatial_coverage`, `primary_key`, `profile` (false when `published` under `queria:` is false), `materialized`, `sql` (not for a view: the metadata holds its SQL), `depends_on`, `source_path` |
| `_fdl.columns` | each column with a `title`, a `description`, an `entity` (its `name`) or `asset: true` |
| `_fdl.files` | the [files in the dataset](#paths-in-the-dataset): `path`, `sha256`, `bytes`, `media_type` |
| `_fdl.catalogs` | the other datasets the SQL reads, by the name it reads them under |
| `_fdl.attributes` | the keys under `queria:` and `annotations:` of the dataset, the tables and the columns |

- A key for one reader becomes the attribute `<reader>-<key>`, with `_` in the key written `-`: `title_kana` under `queria:` is `queria-title-kana`. The value is the JSON of what was written
- `licenses` is a list of `{id, spdx, url, title, commercial_use, share_alike, attribution_required}`; a license written as a string is `{id}`
- The files are not in the catalog. `_fdl.files.sha256` is an asset column: `fdl commit --assets` uploads each file by its content
- The `_fdl` tables are dropped and written again each time, in one transaction. The `_meta` schema tabledoc 0.3 wrote is dropped in it. Without a dbt build (no `sql` in the description), each table keeps the `materialized`, `sql`, `depends_on` and `source_path` the catalog's `_fdl` (or `_meta`) holds
- tabledoc writes no comments (`COMMENT ON`)

## Writing the files from a catalog

`tabledoc dump` writes the files of the description a catalog's `_fdl` holds: `tabledoc.yml`, a table file for each table described, and every file of `_fdl.files` at its path. `tabledoc load` reads them back to the same `_fdl`.

```bash
tabledoc dump --ducklake work.sqlite --out description/
```

- `--ducklake`: the catalog (default: `FDL_WORKING`). `--out`: the folder (default: here), outside `.fdl/`
- `--files`: where the files of `_fdl.files` are, as `<files>/<sha256>`: a folder or an http(s) URL. Default: `assets/` of the repository `fdl clone` noted beside the catalog. Each file is checked against its sha256
- `--name`: the dataset's `name` in `tabledoc.yml`. Default: the last part of the repository's URL
- A file already in the folder is not replaced, and nothing is written, unless `--force`
- Each table file is at `<schema>/<table>.yml`, and its guide at `<schema>/<table>/README.md`. The Markdown files of a folder other than `README.md` are listed in that folder's `docs`
- What `_fdl` does not hold is not written: an entity's type (`primary` for a column that alone is the primary key, else `foreign`), dimensions, granularity, metrics, and the other datasets the SQL reads, which come from dbt's `profiles.yml`. A table that only `--unlisted` wrote gets no table file. `sql` and `depends_on` are written only for a table without a `source_path` (one dbt does not build)

## The older format

So that every dataset need not be rewritten at once, tabledoc also reads the format it replaces. Only tabledoc's format is written anew.

- Without `tabledoc.yml`, `queria.yml` (`https://queria.io/schemas/dataset/v1.json`) is read as `tabledoc.yml`. Its top-level `title_kana`, `themes`, `cover` and `ai_context` are read as if under `queria:`. `catalogs` is used for `depends_on` and returned as `catalogs`
- Markdown whose front matter has `$schema: https://queria.io/schemas/table/v1.json` is read as a table file (the front matter) and its guide (the text below). `table:` says which table, `fields` is `columns`, and `published`, `themes` and `ai_context` are read as if under `queria:`. The guide is that Markdown's path, and what is sent is the text without the front matter
- A field's `semantic: {role, name, agg}` is read as: `role: entity` → `entity: {type: foreign, name}`, or `type: primary` when the column alone is the `primary_key`; `role: dimension` → `dimension: categorical`; `role: measure` → a metric `{name: <column>, agg, expr: <column>}` on the table (without `agg`, a warning)
- `tabledoc.yml` and `queria.yml` in the same folder is an error

## $schema and versions

- tabledoc ships its JSON Schemas and serves them at `https://queria-io.github.io/tabledoc/schemas/<kind>/v<n>.json`. The kinds are `dataset` and `table`
- Adding keys keeps the version. Changing what a key means, or removing one, makes `v2`, and tabledoc reads both for a while
- A file with a `$schema` this tabledoc does not know is refused, with a request to upgrade tabledoc
