# CHANGELOG


## v0.9.0 (2026-11-23)

### Features

- Fill in the licenses tabledoc knows by id ([#25](https://github.com/queria-io/tabledoc/pull/25),
  [`c98b796`](https://github.com/queria-io/tabledoc/commit/c98b79607dc46fae5367a1484b2553936abcb26b))

tabledoc now holds the title, URL and terms of common licenses (SPDX ones and terms of use without
  an SPDX identifier, such as JP-PDL-1.0) in licenses.json. A license written by one of those ids is
  filled in on read, so every catalog holds the same entry; keys written that differ are replaced
  with a warning (known-license). dump writes such a license back as its id alone.

The spec also says what homepage is: the dataset's web page other than its repository.


## v0.8.0 (2026-11-23)

### Features

- Put the primary key in _tabledoc and settle the names of v1
  ([#23](https://github.com/queria-io/tabledoc/pull/23),
  [`b77c39a`](https://github.com/queria-io/tabledoc/commit/b77c39aa8358288a76bc2ef530ab31fcb08730b1))

* feat!: put the primary key in _tabledoc and settle the names of v1

- columns.key_position holds each column's place in the primary key - listed becomes hidden (true
  hides a table); --unlisted becomes --hide-undescribed - sources and contributors take url instead
  of path - entity is the name of a code system; dimension is categorical or time - drop keywords,
  the license spdx key and the schema key of tabledoc.yml - the profile tables use FDL's names
  (rows, min, max, count) and its value rule - the dataset table holds the dataset's name, which
  dump reads back - the spec says how each table was built, and that v1 may still change

BREAKING CHANGE: tabledoc.yml and table files with listed, path, keywords, spdx, schema or an entity
  map are refused, and readers of _tabledoc see the new column names.

* fix: read older keywords as topics and refuse catalogs of earlier tabledoc in dump

* fix: read listed and keywords in dbt config.meta as hidden and topics, keep
  schemas/tabledoc/v1.json

### Breaking Changes

- Tabledoc.yml and table files with listed, path, keywords, spdx, schema or an entity map are
  refused, and readers of _tabledoc see the new column names.


## v0.7.0 (2026-11-23)

### Features

- Read fdl's remote and data path from fdl status --json
  ([#22](https://github.com/queria-io/tabledoc/pull/22),
  [`0fa2a6e`](https://github.com/queria-io/tabledoc/commit/0fa2a6e064330229841c99f2aa3b6523df4d6323))

* feat: read fdl's remote and data path from fdl status --json

tabledoc no longer reads the files fdl keeps beside its working metadata. It runs fdl status --json
  for the remote and the data path, which needs fdl-cli 0.35 or later.

* feat: say that a working metadata from fdl-cli 0.34 needs a newer fdl


## v0.6.1 (2026-11-23)

### Bug Fixes

- Read a table file beside a dbt Python model ([#21](https://github.com/queria-io/tabledoc/pull/21),
  [`2b9b7a6`](https://github.com/queria-io/tabledoc/commit/2b9b7a681cb5916f8f7d4e1fd0eab6c3a324440c))

A dbt model can be a .py file. Accept <model>.tabledoc.yml next to <model>.py as well as
  <model>.sql.


## v0.6.0 (2026-11-23)

### Bug Fixes

- Read fdl's state from <catalog>.fdl/state.json, as fdl keeps it after 0.34
  ([#19](https://github.com/queria-io/tabledoc/pull/19),
  [`9bff5a8`](https://github.com/queria-io/tabledoc/commit/9bff5a8c739639b450c8f84d8dae0528d1f17a6d))

fdl clone keeps its state in <catalog>.fdl/state.json from the release after 0.34. load, dump and
  declare read it there, and from <catalog>.fdl.json as fdl 0.34 wrote it.

### Continuous Integration

- Release on every push to main ([#20](https://github.com/queria-io/tabledoc/pull/20),
  [`7581ea2`](https://github.com/queria-io/tabledoc/commit/7581ea21819ed2564ab9a36f2f4d0f8f70805a6c))

### Features

- Write the description as 20 tables in third normal form, and drop queria:
  ([#18](https://github.com/queria-io/tabledoc/pull/18),
  [`f57a8e8`](https://github.com/queria-io/tabledoc/commit/f57a8e873e1b324c16df57d14b02c2623a444160))

* feat!: write the description as 20 tables in third normal form, and drop queria:

Licenses, sources and contributors get ids, and tables refer to them by id. title_kana is
  title_reading, cover is image, published is listed, and synonyms is a key of its own. A table of
  another dataset in depends_on is <dataset>.<schema>.<table>.

* docs!: define tabledoc as a vocabulary with two forms, files and the _tabledoc tables

* fix: read the older format without breaking existing datasets, and keep tables load did not write

- Read cover as image only when it is a file's path - An entry whose keys all match the entry with
  the same id refers to it - Report a duplicate or unknown id in the file it is written in - Skip a
  source without an id after its schema error, instead of failing - Drop only the texts table an
  earlier tabledoc wrote - dump: refuse a catalog an earlier tabledoc wrote, and sort topics,
  synonyms and depends_on


## v0.5.0 (2026-11-22)

### Features

- Describe each table in <table>.tabledoc.yml beside its SQL, list documents in documents, and layer
  dbt's keys per key ([#17](https://github.com/queria-io/tabledoc/pull/17),
  [`10ff9d3`](https://github.com/queria-io/tabledoc/commit/10ff9d3617a6dbc34c86879d7a873bfcd3e1fdb7))

- Serve the docs and the JSON Schemas from tabledoc.queria.io on Cloudflare Workers
  ([#16](https://github.com/queria-io/tabledoc/pull/16),
  [`17c4436`](https://github.com/queria-io/tabledoc/commit/17c443604c2120440e407cf21f6fc5eeb0dedd34))

* feat!: serve the docs and the JSON Schemas from tabledoc.queria.io on Cloudflare Workers

The site is an assets-only Worker, like docs.queria.io. npm run build copies the JSON Schemas into
  dist/schemas/, served with CORS. Their URLs move from queria-io.github.io/tabledoc/schemas/ to
  tabledoc.queria.io/schemas/; the old ones were never served. GitHub Pages and its workflow are
  removed.

BREAKING CHANGE: $schema is https://tabledoc.queria.io/schemas/<kind>/v1.json

* chore: sync uv.lock with the released version

* fix: refuse the old schema URL, keep Blume's headers, build strictly, and name the custom domain
  in wrangler.jsonc

A file whose $schema is the old queria-io.github.io URL is refused with the new one, instead of
  being skipped. The schema headers are appended to the _headers Blume writes. The account comes
  from the environment, not the file.


## v0.4.0 (2026-11-22)

### Features

- Return the other datasets the SQL reads as dependencies, in the shape of FDL's tables.json
  ([#12](https://github.com/queria-io/tabledoc/pull/12),
  [`980df25`](https://github.com/queria-io/tabledoc/commit/980df258de9e8e1a1b044ba49d8813fe9561900e))


## v0.3.1 (2026-11-22)

### Bug Fixes

- Export --markdown writes text in the dataset's language
  ([#13](https://github.com/queria-io/tabledoc/pull/13),
  [`0cbda91`](https://github.com/queria-io/tabledoc/commit/0cbda917557e30989c548eadbded8ba7a97fa223))

- Keep an export inside the root out of the next read, and refuse what export cannot write
  ([#15](https://github.com/queria-io/tabledoc/pull/15),
  [`a5034bf`](https://github.com/queria-io/tabledoc/commit/a5034bf21760a603ffaab8f25d5c1dc19d90c8b8))

- Keep recognizing earlier description schemas, refuse empty text, compare tags without case
  ([#14](https://github.com/queria-io/tabledoc/pull/14),
  [`627e072`](https://github.com/queria-io/tabledoc/commit/627e0721debebf91c3f7553ebf96f704b46d23a9))


## v0.3.0 (2026-11-22)

### Features

- Mark the tables Queria does not list with "profile": false in dataset.json
  ([#6](https://github.com/queria-io/tabledoc/pull/6),
  [`fae794f`](https://github.com/queria-io/tabledoc/commit/fae794f21bf1288164f6a812e9b56e86c05fa7ff))

- Tabledoc export --markdown writes one Markdown file per table for AI to read
  ([#10](https://github.com/queria-io/tabledoc/pull/10),
  [`b2d8fca`](https://github.com/queria-io/tabledoc/commit/b2d8fca31619936304d8e108266c94e28687ec33))

- Write names, descriptions and topics in more than one language
  ([#9](https://github.com/queria-io/tabledoc/pull/9),
  [`727289b`](https://github.com/queria-io/tabledoc/commit/727289bc3dda8ebc820d141514b71798d26d20e3))

- Write the description into ordinary tables of a schema, and add tabledoc dump
  ([#7](https://github.com/queria-io/tabledoc/pull/7),
  [`4d88f7d`](https://github.com/queria-io/tabledoc/commit/4d88f7d1418802d0bc943e438a866808e81492ff))


## v0.2.0 (2026-11-21)

### Documentation

- Add the documentation site built with Blume ([#2](https://github.com/queria-io/tabledoc/pull/2),
  [`6ae0f45`](https://github.com/queria-io/tabledoc/commit/6ae0f45226b14c62197e24fed1345c0a3f23f95e))

Serve docs/ (English) and docs/ja/ (Japanese) at tabledoc.queria.io with the JSON Schemas under
  schemas/, from one Pages deployment.

### Features

- Tabledoc load writes the description into a DuckLake catalog's _meta schema
  ([#5](https://github.com/queria-io/tabledoc/pull/5),
  [`1957812`](https://github.com/queria-io/tabledoc/commit/1957812e63e9261f853ec30c652aacb75711c394))


## v0.1.0 (2026-11-17)


## v0.0.0 (2026-11-17)

### Chores

- Add the license
  ([`705af18`](https://github.com/queria-io/tabledoc/commit/705af18f4889d5fa4bc5c2bfe724c6226c20bad3))
