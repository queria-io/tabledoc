# CHANGELOG


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
