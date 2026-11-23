---
title: Specification (v1)
sidebar:
  label: Specification
  order: 2
description: The vocabulary for describing a dataset, its two forms (files and tables), and what the tabledoc CLI does with them.
---

tabledoc is a convention for describing a dataset to people: what each table and column means, its licenses, sources and contributors, and the guides that go with it. The same vocabulary has two forms:

- Files an author writes: YAML and Markdown, or a dbt project's yml ([Files](#files))
- Tables in the database next to the data: the tables of the schema `_tabledoc` ([The tables](#the-tables))

A program reads either form, and the two hold the same description. The tables use only text, booleans and integers, so any database with SQL schemas can hold them: DuckLake, Iceberg, PostgreSQL or BigQuery. tabledoc keeps no history; the catalog that holds the tables versions them with the data (a DuckLake snapshot, an FDL version), and where it does not, the files are kept in Git.

The `tabledoc` command is the reference implementation. It checks the files, writes them into the tables of a DuckLake catalog (`tabledoc load`), writes the files back from the tables (`tabledoc dump`), and writes Markdown for AI assistants and people to read (`tabledoc export --markdown`).

## Commands

- `tabledoc validate`: check the author's files
- `tabledoc load`: check them and write the description into the tables of a DuckLake catalog ([Writing into a DuckLake catalog](#writing-into-a-ducklake-catalog))
- `tabledoc dump`: write the files of the description a catalog holds ([Writing the files from a catalog](#writing-the-files-from-a-catalog))
- `tabledoc export --markdown`: check them and write them as Markdown, one file per table ([Writing Markdown for AI](#writing-markdown-for-ai))

It exits with 1 when there are errors (with `--strict`, warnings too) and 2 when the files or the catalog cannot be read or written at all.

## Files

Paths are relative to the folder that holds `tabledoc.yml` (the root).

```
tabledoc.yml              the dataset (the name is fixed)
README.md                 the dataset's overview (optional)
<schema>/<table>.tabledoc.yml   a table
<schema>/<table>.md             the table's guide (optional)
```

One table is described in one file, and its name and place decide which table. Every other document is listed by path under `documents` ([guides and documents](#guides-and-documents)), so it can be kept anywhere under the root.

In a dbt project, a table file sits next to its model's `.sql` instead: `<model>.tabledoc.yml` and `<model>.md` beside `<model>.sql`. dbt's yml can keep to what the build needs, such as tests ([dbt projects](#dbt-projects)).

Folders whose name starts with `.`, and `target/`, `dbt_packages/`, `node_modules/` and `.venv/`, are not read.

## tabledoc.yml

The description of one dataset.

```yaml
$schema: https://tabledoc.queria.io/schemas/dataset/v1.json
name: boj
title: Bank of Japan time-series statistics
title_reading: ニチギンジケイレツトウケイ
description: Every statistic on the Bank of Japan's time-series data search site.
language: en
topics: [Bank of Japan, interest rates, prices]
synonyms: [BOJ statistics]
homepage: https://github.com/queria-io/dataset-boj
update_frequency: irregular
licenses:
  - id: boj-copyright
    title: Bank of Japan copyright and disclaimer
    url: https://www.boj.or.jp/en/about/copyright.htm
sources:
  - id: search-site
    title: Bank of Japan time-series data search site
    url: https://www.stat-search.boj.or.jp/
contributors:
  - id: boj
    title: Bank of Japan
    url: https://www.boj.or.jp/
    roles: [rightsHolder]
spatial_coverage: [JP]
image: docs/cover.png
schemas:
  - name: timeseries
    title: Time series
documents:
  - docs/methodology.md
```

| Key | Required | Meaning |
| --- | --- | --- |
| `$schema` | yes | The format and its version |
| `name` | yes | The dataset's name: `^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$` |
| `title`, `title_reading`, `description`, `topics`, `synonyms`, `homepage`, `language`, `issued`, `update_frequency` | | `title_reading` is how the title is read (its kana in Japanese, say); `synonyms` are other names people search for it by; `language` is a BCP 47 tag, the language of the text written without one ([languages](#languages)); `issued` is `YYYY-MM-DD`; `update_frequency` is `continuous`, `daily`, `weekly`, `monthly`, `quarterly`, `yearly` or `irregular` |
| `repository` | | The URL of the repository of the dataset's source code, such as `https://github.com/queria-io/dataset-boj`. `tabledoc load` takes Git's `origin` when it is left out |
| `licenses`, `sources`, `contributors`, `temporal_coverage`, `spatial_coverage` | | [Licenses, sources and contributors](#licenses-sources-and-contributors). Written in a table file, `licenses`, `sources` and the coverage are that table's alone |
| `image` | | The path of an image that stands for the dataset. It is sent with the documents and keeps its path under the root |
| `schemas` | | `name`, `title`, `title_reading`, `description`, `topics`, `synonyms`, `documents` (the schema's documents) |
| `documents` | | Paths of the dataset's documents |
| `annotations` | | Keys for other readers, by the reader's name ([keys for other readers](#keys-for-other-readers)) |

## Table files

The description of one table. A table file is a YAML file named `<table>.tabledoc.yml` whose `$schema` is `https://tabledoc.queria.io/schemas/table/v1.json`. Other YAML files (dbt's yml, say) are not read as table files. The keys follow one entry of dbt's `models:`; keys dbt does not have (`title`, `primary_key`, `sources` and so on) sit at the same level.

```yaml
$schema: https://tabledoc.queria.io/schemas/table/v1.json
name: series
title: Series
description: |-
  Every series of every database on the search site. One row is one series.
primary_key: [db, series_code]
sources: [search-site]
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
| `name` | The table's name. The same as the file name when written ([which table](#which-table)) |
| `title`, `title_reading`, `description`, `topics`, `synonyms` | `topics` as a repository's topics on GitHub |
| `hidden` | `true` keeps the table out of lists and search, such as a table only other tables read. Default `false` |
| `primary_key` | The columns that identify a row |
| `licenses`, `sources`, `temporal_coverage`, `spatial_coverage` | Only when they differ from the dataset's |
| `sql`, `depends_on` | For a table dbt does not build: the SQL it is made from and the tables it reads |
| `documents` | Paths of the table's documents |
| `columns` | `name`, `title`, `title_reading`, `description`, `topics`, `synonyms`, `asset`, and the semantic keys `entity`, `dimension`, `granularity` |
| `metrics` | How the table is aggregated ([semantics](#semantics)) |
| `annotations` | Keys for other readers |

Types, nullability and row counts are not written. The data store holds the structure.

`asset: true` says the column's value is the path of a file that belongs to the row.

## Which table

- The name and place decide: `<schema>/<table>.tabledoc.yml` describes `<schema>.<table>`. A file directly under the root is in the `main` schema
- In a dbt project, `<model>.tabledoc.yml` next to the model's file (`<model>.sql`, or `<model>.py` for a Python model) describes that model's table, named by the model's `schema` and `alias`. A table file there with no model beside it is an error
- A table file anywhere else, or a `name` other than the file name, is an error
- dbt parses every yml under its model paths, and a table file's `sources` is not what dbt's `sources:` is. A dbt project with table files lists `*.tabledoc.yml` in `.dbtignore`; without it, tabledoc gives an error

## Licenses, sources and contributors

Each license, source and contributor has an `id`: short, fixed, and unique in the dataset. The tables refer to them by it, so a title can be corrected without changing what refers to it.

```yaml
licenses:
  - CC-BY-4.0                       # an id alone
  - id: boj-copyright
    title: Bank of Japan copyright and disclaimer
    url: https://www.boj.or.jp/en/about/copyright.htm
sources:
  - id: search-site
    title: Bank of Japan time-series data search site
    url: https://www.stat-search.boj.or.jp/
```

- An entry is written in full once, in `tabledoc.yml` or in any table file, and by its `id` alone anywhere else (`sources: [search-site]`)
- An entry whose keys all match the entry with the same `id` (`{id, path}` beside `{id, title, path}`, say) refers to it. Two entries with the same `id` that differ in a key are an error
- A license whose `id` is written alone and defined nowhere is that `id` (an SPDX identifier such as `CC-BY-4.0`, say). A license that has an SPDX identifier takes it as its `id`. A source whose `id` is defined nowhere is an error
- A license is `{id, url, title, commercial_use, share_alike, attribution_required}`, a source `{id, title, url}`, and a contributor `{id, title, url, roles}`. Contributors are the dataset's only

## Languages

Text people read can be written in more than one language. Write the value as a map from a BCP 47 tag to the text, or as the text alone, which is in the dataset's `language`.

```yaml
language: ja
title:
  ja: 日本銀行時系列統計
  en: Bank of Japan time-series statistics
topics:
  ja: [日本銀行, 金利]
  en: [Bank of Japan, interest rates]
columns:
  - name: db
    title: {ja: データベース, en: Database}
    description: databases の db と同じ
```

- Any of tabledoc's keys whose value is text, or a list of text, takes either form: `title`, `title_reading`, `description`, `topics`, `synonyms`, `homepage`, and the `title` and `url` of licenses, sources and contributors, say. A list becomes a map from a tag to a list
- Values that point at something, or come from a fixed set, hold one value: `name`, `table`, `repository`, `primary_key`, `entity`, `language`, `$schema`, `issued`, `update_frequency`, `dimension`, `granularity`, `agg`, `expr`, `sql`, `depends_on`, `id`, `roles`, `hidden`, `image`, `spatial_coverage`, `temporal_coverage`, and the paths in `documents`. Written in other languages, they would no longer point at the same table, column or file
- The tables hold the text of `title`, `title_reading`, `description`, `topics` and `synonyms` in every language. Of the other text (`homepage`, licenses, sources, contributors and a metric's `description`) they hold the one in `language`, and tabledoc warns when it is written in more
- Keys under `annotations:` are the reader's own
- A tag is checked as BCP 47. A map with no text is an error
- In a dbt project's yml, `description` is the text alone, in `language`. dbt does not take a map there
- `tabledoc.read` returns these values as maps always: the text alone becomes `{<language>: text}`, and `{und: text}` without `language`

## Guides and documents

- Documents are listed by path in `documents`: the dataset's in `tabledoc.yml`, a schema's in `schemas[].documents`, a table's in its table file. Paths are relative to the root, and the file can be anywhere under it
- A document named `README.md` describes the thing it is listed under; it is the thing's guide. The others keep their names
- Two documents are listed without being written: `README.md` at the root is the dataset's, and the `.md` with the same name next to a table file (`series.md` for `series.tabledoc.yml`, or for `series.sql` in a dbt project) is that table's guide
- Two guides for one thing is an error (a table's `series.md` and a `README.md` in its `documents`, say)
- A `README.md` in a schema's folder or in `<schema>/<table>/` that no `documents` lists is not read, with a warning
- Documents have no front matter
- The files a Markdown document links to with a relative path (images, PDFs, other documents) are sent too. A link that leaves the root is an error; a link to a missing file is a warning; a link to a folder is left alone
- Build and maintenance notes belong in `CONTRIBUTING.md`, not in `documents`

### Paths in the dataset

In the dataset, each folder is one thing described: the root is the dataset, `<schema>/` a schema, `<schema>/<table>/` a table. The folder's `README.md` describes it, and its other files are its documents. tabledoc places the files there, wherever the author keeps them:

| Written | Path in the dataset |
| --- | --- |
| an entry of the dataset's `documents` | `<file name>` |
| an entry of `schemas[].documents` | `<schema>/<file name>` |
| an entry of a table's `documents` | `<schema>/<table>/<file name>` |
| a table's guide (next to its table file or model) | `<schema>/<table>/README.md` |
| a file a document links to | its path under the root |

- In a Markdown document, each relative link to a file that was placed elsewhere is rewritten to point at its new path. The `sha256` and `bytes` are those of the rewritten document
- Two files at the same path in the dataset is an error, and so is one file named for two paths in the dataset (the same document in two tables' `documents`, say)

## dbt projects

When the root has `dbt_project.yml`, tabledoc reads `target/manifest.json` (`--manifest` changes it). Run `dbt compile` (or a build) first; without a manifest, tabledoc warns and reads only the table files. `load` gives this as info instead when the catalog has a table dbt built (one with a `source_path`), the description has no `sql`, and it describes each such table, since it keeps their SQL.

- The tables are the enabled models materialized as `table`, `view` or `incremental`, under the model's `schema` and `alias`. Ephemeral and disabled models, seeds, snapshots and tests make no table, so they are not listed. A model with no description is listed with what dbt fills in only (`materialized`, `sql`, `depends_on`, `source_path`)
- What dbt has a key for is read from dbt: the model's and the columns' `description`, the primary key from `constraints` (`type: primary_key`, on the model or on one column), and semantics from the columns' `entity` (its `name`), `dimension` (its `type`) and `granularity` and the semantic layer's simple `metrics`
- What dbt has no key for (`title`, `title_reading`, `topics`, `synonyms`, `hidden`, `sources`, `licenses`, `documents`, a column's `title` and `asset`, and so on) is added in either of two places: `config.meta` of the model and of each column in dbt's yml, or the table file `<model>.tabledoc.yml` next to the model's `.sql`. The table file keeps each table's description in a file of its own and dbt's yml to the build; `config.meta` is read for teams that already write there
- dbt's own keys, `config.meta` and the table file are read together, key by key (and column by column, key by key). A key written in two of them is an error: an empty `description` in dbt counts as not written, and `primary_key` in `config.meta` or a table file beside dbt's `constraints` is an error too
- A program that changes the description writes each key where it is now, and a key that is not written yet into the table file, so it never rewrites dbt's yml
- `materialized` is the model's materialization, `source_path` its `original_file_path`, and `sql` its `compiled_code`. `depends_on` is read from it by DuckDB's parser. A table of another dataset is written `<dataset>.<schema>.<table>`, where `<dataset>` is the name the SQL attaches it under; its URL comes from the DuckLake ATTACHes in `profiles.yml` (`--profiles`, else `DBT_PROFILES_DIR`, else the root)
- A guide is the `.md` with the same name next to the model's `.sql` (dbt ignores `.md` files without a docs block), or one of the table's `documents` named `README.md`

```yaml
models:
  - name: series
    description: One row is one series.
    config:
      meta:
        title: Series
    constraints:
      - type: primary_key
        columns: [db, series_code]
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
| `entity` | the name of a code system, such as `corporate_number` or `city` | The column is an identifier: its values come from that code system, so it joins with the columns of other tables and datasets that name the same one. Whether it identifies the row is the primary key's to say |
| `dimension` | `categorical` or `time` | A column to filter and group by |
| `granularity` | `day`, `month`, `year`, ... | How fine a `dimension: time` column is |
| `metrics` (table) | `[{name, agg, expr, description}]` | How to aggregate. `agg` is `sum`, `max`, `count_distinct`, ... |

In dbt, `metrics` need the semantic layer (`semantic_model: true` and a time spine). A project that does not use it can still write `entity` and `dimension` on columns.

## Keys for other readers

Keys only one reader uses go under `annotations: {<reader>: {...}}`, in `tabledoc.yml`, a table file or a column. tabledoc does not check them, returns them as written, and does not write them into the tables. A key that any reader can use belongs in tabledoc's vocabulary instead.

## Reading from Python

Programs that send the description somewhere, or turn it into another format, read it with `tabledoc.read`. It checks the files as `validate` does and returns the description with the older formats read as today's.

```python
import tabledoc

report = tabledoc.Report()
d = tabledoc.read(tabledoc.Options(root), report)  # root: the folder of tabledoc.yml
if report.failed:
    print(report.render())
d.dataset   # {"name": "boj", "title": …, "documents": ["README.md", "methodology.md"], "image": "docs/cover.png"}
d.schemas   # [{"name": "timeseries", "title": "Time series"}]
d.tables    # [{"schema": "timeseries", "name": "series", "sql": …, "depends_on": […], "documents": ["timeseries/series/README.md"], "columns": […]}]
d.files     # [File(path="README.md", sha256="…", bytes=1234, media_type="text/markdown", local="README.md"), …]
d.source    # {"repository": "https://github.com/…", "commit": "…", "path": "", "dirty": False}
d.dependencies  # {"other": {"url": "https://…"}}: the other datasets the SQL reads, by the name it reads them under, as `dependencies` of FDL's tables.json
d.content(d.files[0])  # the bytes of that file
```

- `source` is the Git working copy: `repository` is the `origin` remote as an https URL (without credentials or `.git`), `commit` is HEAD, `path` goes from the repository's root to the folder of `tabledoc.yml`, and `dirty` says whether there were changes not committed. It is None outside Git, or with `Options(with_source=False)`
- Documents are referred to by their [paths in the dataset](#paths-in-the-dataset). `files` lists every file whose content is meant to go with the description (the documents and what they link to) with that path, its sha256, size and media type, and `local`, its path under the root. Each `documents`, `schemas[].documents` included, lists paths in `files`; the one whose name is `README.md` is the guide. `content` gives what goes into the dataset for a file: its bytes, a Markdown document with its links rewritten, and for an older-format Markdown table file, the text without its front matter
- Licenses and sources written by their `id` alone come out as the entry that defines them
- Tables are sorted by `schema`, then `name`, and keys come in a fixed order. The same files give the same records
- The structure (types, nullability, row counts, whether a table is a view) is not in it

## The tables

The description as tables: those of one schema, `_tabledoc`, in the database that holds the data. They are in third normal form: every cell holds one value (no lists, structs or JSON), and each fact is in one row of one table.

- `schema_name`, `table_name` and `column_name` name what a row is about. A part that does not apply is `''`: a row about the dataset has all three `''`, a row about a schema has `table_name` and `column_name` `''`, and a row about a table has `column_name` `''`
- A column that refers to a row of another table is named `<the other table, singular>_<its key>`: `license_id`, `source_id`, `contributor_id`
- Table names are plural, but `dataset`, which has one row for each key
- The database has no foreign keys for them. A writer checks that each row refers to rows that are there
- The tables hold only the description as it is now. The catalog keeps the earlier versions

| Table | Primary key | Other columns |
| --- | --- | --- |
| `dataset` | `key` | `value`. The keys are `name`, `language`, `homepage`, `repository`, `issued` (`YYYY-MM-DD`), `update_frequency`, `image` (a `path` of `files`), `temporal_start` and `temporal_end` |
| `schemas` | `schema_name` | |
| `tables` | `schema_name`, `table_name` | `hidden` (`false` unless the description says `true`), `temporal_start`, `temporal_end`, `sql`, `source_path` |
| `columns` | `schema_name`, `table_name`, `column_name` | `key_position` (the column's place in the primary key, from 0; NULL when it is not in it), `entity` (the name of the code system its values come from, such as `city`), `dimension` (`categorical` or `time`), `granularity` |
| `metrics` | `schema_name`, `table_name`, `metric_name` | `agg`, `expr`, `description` |
| `descriptions` | `schema_name`, `table_name`, `column_name`, `language` | `title`, `title_reading`, `description` |
| `topics` | `schema_name`, `table_name`, `column_name`, `language`, `topic` | |
| `synonyms` | `schema_name`, `table_name`, `column_name`, `language`, `synonym` | |
| `licenses` | `id` | `url`, `title`, `commercial_use`, `share_alike`, `attribution_required` |
| `table_licenses` | `schema_name`, `table_name`, `license_id` | `position` |
| `sources` | `id` | `title`, `url` |
| `table_sources` | `schema_name`, `table_name`, `source_id` | `position` |
| `contributors` | `id` | `title`, `url`, `position` |
| `contributor_roles` | `contributor_id`, `role` | |
| `table_areas` | `schema_name`, `table_name`, `area` | `position` (the areas of `spatial_coverage`) |
| `table_dependencies` | `schema_name`, `table_name`, `depends_on` | (a table this dataset holds is `<schema>.<table>`, one of another `<dataset>.<schema>.<table>`) |
| `files` | `path` | `sha256`, `bytes`, `media_type` ([the files in the dataset](#paths-in-the-dataset)) |

- `descriptions`, `topics` and `synonyms` are about the dataset, a schema, a table or a column. `table_licenses`, `table_sources` and `table_areas` are about the dataset or a table
- `position` keeps the order they are written in, from 0
- A column that holds a date or a number in the files (`issued`, `temporal_start`) holds it as text
- `files` names each document and what it links to by its sha256. The files themselves are stored by the catalog or beside it (with FDL, as the dataset's assets)
- A table has a row in `columns` for each column described and each column of its primary key
- Whether a column holds the path of a file (`asset`) is not in these tables. The catalog holds it (with FDL, as a declaration)

### How each table was built

Three parts of the tables say how a table was built, not what it means: `tables.sql`, `tables.source_path` and `table_dependencies`. People do not write them; a tool fills them in from the build (from dbt's manifest, by `tabledoc load`). A reader shows them as a table's lineage, and a build can compare `sql` with the last version's to skip a table whose SQL did not change.

### Profiles

Three more tables hold what was counted in the data, so that readers can search by it. They are optional. People do not write them; a program counts them from the data (the column statistics of DuckLake or Iceberg, or an SQL query) and writes them again when the data changes, without merging. They hold what [an FDL profile](https://fdl.queria.io/spec/versions#profiles) holds, under the same names.

| Table | Primary key | Other columns |
| --- | --- | --- |
| `table_profiles` | `schema_name`, `table_name` | `rows` |
| `column_profiles` | `schema_name`, `table_name`, `column_name` | `null_count`, `distinct_count`, `min`, `max` (as text) |
| `column_values` | `schema_name`, `table_name`, `column_name`, `value` | `count`: the rows that hold the value. Every value of a column with 2,000 distinct values or fewer, else its 10 most common |

With FDL, each version has these profiles as FDL's own files, and these tables are not written. Searching across datasets is the reader's work: it gathers the tables of each dataset into an index of its own.

## Writing into a DuckLake catalog

`tabledoc load` checks the description as `validate` does, then writes it into the [tables](#the-tables) of a [DuckLake](https://ducklake.select) catalog: those of the schema `_tabledoc`, unless `--schema` names another. With fdl, the catalog is the working metadata `fdl clone` makes, and `fdl commit` makes a version of it.

```bash
tabledoc load --ducklake work.sqlite --out build/assets
fdl commit work.sqlite -m "..." --assets build/assets
```

- `--ducklake`: the catalog (default: `FDL_WORKING`). `--data-path`: where new data files go (default: `FDL_DATA_PATH`, else the `data_path` that `fdl status --json` gives for fdl's working metadata). Data files over HTTP are read with DuckDB's secrets; when the catalog is fdl's working metadata and `FDL_TOKEN` is set, the token is sent to the `remote` that `fdl status --json` gives, so a private dataset's files can be read
- `--schema`: the schema to write into (default: `_tabledoc`)
- `--out`: also write the folder `fdl commit --assets` takes: each file of the `files` table under `files/<path>`. With `--assets <folder>`, the files below it (those of the build's asset columns) are linked under `data/`. The folder has to be empty or written by an earlier `load`, and outside `.fdl/`, which only fdl writes
- `--hide-undescribed`: the catalog's tables and views that have no description get a row in `tables` with `hidden` true, and so does a table dbt built that the author described nowhere (only its SQL is known). The tables of the schema written into, and of each schema that holds the tables `dataset`, `schemas`, `tables`, `columns` and `files` (one an earlier load wrote into), get none
- A described table or column, or a primary key column, that is not in the catalog is an error, and so is an `asset` column that is not `varchar`. Names match without regard to case, as in DuckDB, and are written as the catalog spells them
- A value its column cannot hold (`issued` other than `YYYY-MM-DD`, say), and a row that refers to a row that is not there, are errors
- On an error (with `--strict`, a warning) nothing is written
- Rows are added, changed and removed by their primary key, so a load changes only the cells that differ. Without a dbt build (no `sql` in the description), each table keeps the `sql`, `source_path` and `table_dependencies` the catalog holds
- `source_path` is the path of the file that defines the table, from the root of `repository` (dbt's `original_file_path`, under the folder of `tabledoc.yml` in the Git working copy), and `sql` is the SQL that made it; both are NULL where they are not known. Whether it is a table or a view is not written: the catalog holds that
- A view's row has no `sql` and no `table_dependencies`: the metadata holds the view's SQL
- `repository` is `repository` in `tabledoc.yml`, else Git's `origin` as https
- The tables an earlier tabledoc wrote that are not of the format (`texts`) are dropped, and so are the columns of the format's tables that are not. Other tables of the schema are left as they are. `load` does not write the profile tables, and leaves them as they are
- Asset columns are not written into these tables. When the catalog is the working metadata `fdl clone` made (the folder `<catalog>.fdl` is beside it), `load` declares them to FDL with `fdl declare`, which has to be on `PATH` (fdl-cli 0.35 or later): each table's `primary_key` and the asset columns of each table whose columns say `asset` (a view has neither), no profile for each table and view whose `hidden` is true and a profile for each other table described, the other datasets the SQL reads (from dbt's `profiles.yml`) as dependencies, and the keys of these tables with `files.sha256` as an asset column and no profile. It runs only what differs from `fdl declare list`, and leaves what the description does not say as FDL has it
- tabledoc writes no comments (`COMMENT ON`)

## Writing the files from a catalog

`tabledoc dump` writes the files of the description a catalog holds: `tabledoc.yml`, a table file for each table described, and every file of the `files` table at its path. `tabledoc load` reads them back to the same tables.

```bash
tabledoc dump --ducklake work.sqlite --out description/
```

- `--ducklake`: the catalog (default: `FDL_WORKING`). `--schema`: the schema the description is in (default: `_tabledoc`). `--out`: the folder (default: here), outside `.fdl/`
- `--files`: where the files of the `files` table are, as `<files>/<sha256>`: a folder or an http(s) URL. Default: `assets/` of the `remote` that `fdl status --json` gives for fdl's working metadata. Each file is checked against its sha256
- `--name`: the dataset's `name` in `tabledoc.yml`. Default: the `name` the `dataset` table holds, else the last part of the repository's URL
- A file already in the folder is not replaced, and nothing is written, unless `--force`. A path in the catalog that would leave the folder is an error
- Each table file is at `<schema>/<table>.tabledoc.yml`. Every file stays at its path in the dataset, and the Markdown files of a folder (its `README.md` first) are listed in the `documents` of what the folder describes; the root's `README.md` is the dataset's without being listed
- Text is written as the text alone when there is one language and it is the dataset's `language`, and as a map otherwise
- A license or source is written in full where it is first used (the dataset first, then the tables by name) and by its `id` alone after that; a license that has only its `id` is written as the `id`
- What the tables do not hold is not written: asset columns, `annotations`, and the other datasets the SQL reads, which come from dbt's `profiles.yml`. A table that only `--hide-undescribed` wrote gets no table file. `sql` and `depends_on` are written only for a table without `source_path` (one dbt does not build)

## Writing Markdown for AI

`tabledoc export --markdown <folder>` checks the description as `validate` does, then writes it as Markdown: one file for the dataset, one for each schema and one for each table. AI assistants and people read the folder as it is, or it is published with the data's documentation.

```bash
tabledoc export --markdown ai-docs/
```

| File | Content |
| --- | --- |
| `README.md` | The dataset's title, description, licenses, sources and the other keys of `tabledoc.yml`; its schemas and tables, each with a link and the first paragraph of its description; its documents; then its overview (`README.md`) |
| `<schema>/README.md` | The schema's title and description, its tables and documents, then its guide |
| `<schema>/<table>/README.md` | The table's title, description, primary key, licenses, sources, `materialized`; its columns (title, description, semantics, `asset`) and metrics as tables; the tables it reads and the tables that read it, as links when they are in the dataset; its SQL; its documents; then its guide |

- The files are at the [paths in the dataset](#paths-in-the-dataset), and every other file of `files` (documents, images) is written at its path too, so the links in the guides keep working
- A guide comes after a rule (`---`) as written. Its headings are not changed
- Text written in more than one language is written in the dataset's `language` (else the undetermined one, else the first by tag)
- Keys for other readers (`annotations:`) are not written
- Types, nullability and row counts are not in the description, so they are not written either
- A file already in the folder is not replaced, and nothing is written, unless `--force`. Files of an earlier export that are no longer written stay in the folder
- The folder also gets a `.tabledoc-export` file. tabledoc does not read the files under a folder that holds one, so the folder can be inside the root
- On an error (with `--strict`, a warning) nothing is written

## The older format

So that every dataset need not be rewritten at once, tabledoc also reads the format it replaces. Only tabledoc's format is written anew.

- Without `tabledoc.yml`, `queria.yml` (`https://queria.io/schemas/dataset/v1.json`) is read as `tabledoc.yml`. `title_kana` is read as `title_reading`, `keywords` as `topics`, `cover` as `image` when it is a file's path (one with an extension; an emoji is not read), and `synonyms` under `ai_context` as `synonyms`; `themes` and the rest of `ai_context` are not read. `catalogs` is used for `depends_on` and returned as `dependencies`
- A source's or contributor's `path`, in either older file, is read as its `url`. One without an `id` gets its `path` (else its `title`) as its `id`
- Markdown whose front matter has `$schema: https://queria.io/schemas/table/v1.json` is read as a table file (the front matter) and its guide (the text below). `table:` says which table, `fields` is `columns`, `keywords` is `topics`, `published: false` is `hidden: true` (and `published: true` is `hidden: false`), and `ai_context` and `themes` are read as in `queria.yml`. The guide is that Markdown's path, and what is sent is the text without the front matter
- A field's `semantic: {role, name, agg}` is read as: `role: entity` → `entity: <name>`; `role: dimension` → `dimension: categorical`; `role: measure` → a metric `{name: <column>, agg, expr: <column>}` on the table (without `agg`, a warning)
- `docs` (and `schemas[].docs`) is read as `documents`, and a schema's `guide` as one of its `documents`
- In dbt's `config.meta`, `docs` is read as `documents`, `listed: false` as `hidden: true`, and `keywords` as `topics`
- `tabledoc.yml` and `queria.yml` in the same folder is an error

## $schema and versions

- tabledoc ships its JSON Schemas and serves them at `https://tabledoc.queria.io/schemas/<kind>/v<n>.json`. The kinds are `dataset` and `table`
- Adding keys keeps the version. Until `v1` is fixed, its keys may still be renamed or removed; tabledoc then reads only the keys of this page. Once it is fixed, changing what a key means, or removing one, makes `v2`, and tabledoc reads both for a while
- A file with a `$schema` this tabledoc does not know is refused, with a request to upgrade tabledoc
