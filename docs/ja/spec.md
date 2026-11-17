---
title: 仕様 (v1)
sidebar:
  label: 仕様
  order: 2
description: tabledoc が読むファイル、その検査、作る tabledoc.json を定めます。
---

tabledoc は、人が書くデータセットの説明 (YAML と Markdown、または dbt のプロジェクトの yml) を読み、機械が読む 1 つの JSON (`tabledoc.json`) を作るツールです。特定のデータの置き場や配信先には依存しません。

`tabledoc.json` は dbt の `manifest.json` と同じ扱いで、人は編集しません。書き手のファイルが正です。

## コマンド

- `tabledoc validate`: 書き手のファイルを検査します
- `tabledoc build`: 検査して `target/tabledoc.json` を書きます
- `tabledoc push <URL>`: `target/tabledoc.json` と、そこに並べたファイルを受け手に送ります ([push](#push))

`validate` と `build` は、エラーがあると終了コード 1 (`--strict` では警告も)、ファイルを読めないときは 2 で終わります。

## ファイル

パスは `tabledoc.yml` のあるフォルダ (以下ルート) からの相対パスです。

```
tabledoc.yml              データセット (名前は固定)
README.md                 データセットの概要 (任意)
<schema>/<table>.yml      テーブル
<schema>/<table>.md       テーブルのガイド (任意)
```

dbt のプロジェクトでは、テーブルの説明を dbt の yml に書き、ガイドをモデルの `.sql` の隣に同じ名前の `.md` で置きます ([dbt のプロジェクト](#dbt-のプロジェクト))。

`.` で始まるフォルダと、`target/`・`dbt_packages/`・`node_modules/`・`.venv/` は読みません。

## tabledoc.yml

データセット 1 つの説明です。

```yaml
$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json
name: boj
title: 日本銀行 時系列統計
description: 日本銀行の時系列統計データ検索サイトの全ての統計です。
language: ja
keywords: [日本銀行, 金利, 物価]
homepage: https://github.com/queria-io/dataset-boj
update_frequency: irregular
licenses:
  - id: boj-copyright
    title: 日本銀行 著作権・免責事項
    url: https://www.boj.or.jp/about/copyright.htm
sources:
  - title: 日本銀行 時系列統計データ検索サイト
    path: https://www.stat-search.boj.or.jp/
contributors:
  - title: 日本銀行
    path: https://www.boj.or.jp/
    roles: [rightsHolder]
spatial_coverage: [JP]
schemas:
  - name: timeseries
    title: 時系列統計
docs:
  - docs/methodology.md
queria:
  themes: [economy]
```

| キー | 必須 | 内容 |
| --- | --- | --- |
| `$schema` | 必須 | 書式とバージョン |
| `name` | 必須 | データセットの名前。`^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$` |
| `title`・`description`・`keywords`・`homepage`・`language`・`issued`・`update_frequency` | | `language` は BCP 47 のタグ、`issued` は `YYYY-MM-DD` |
| `licenses`・`sources`・`contributors`・`temporal_coverage`・`spatial_coverage` | | テーブルのファイルに書くと、そのテーブルだけの値になります |
| `schemas` | | `name`・`title`・`description`・`guide` (スキーマのガイドのパス) |
| `docs` | | どのテーブルにも属さない文書のパス。この順で並べます |
| `queria` | | Queria だけが読むキー ([読み手ごとのキー](#読み手ごとのキー)) |
| `annotations` | | ほかの読み手のキー。読み手の名前ごとに書きます |

## テーブルのファイル

テーブル 1 つの説明です。`$schema` が `https://queria-io.github.io/tabledoc/schemas/table/v1.json` の YAML をテーブルのファイルとして読み、`$schema` の無い YAML (dbt の `schema.yml` など) は読みません。キーは dbt の `models:` の 1 項目と同じで、dbt に無いキー (`title`・`primary_key`・`sources` など) は同じ階層に並べます。

```yaml
$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json
name: series
title: 系列の一覧
description: |-
  検索サイトの全 DB の系列の一覧です。1 行が 1 系列です。
primary_key: [db, series_code]
sources:
  - path: https://www.stat-search.boj.or.jp/
columns:
  - name: db
    title: DB 名
    description: databases の db と同じ
    dimension: categorical
  - name: series_code
    title: 系列コード
  - name: last_update
    title: 最終更新日
    dimension: time
    granularity: day
```

| キー | 内容 |
| --- | --- |
| `name` | テーブル名。省くとファイル名 |
| `table` | `<schema>.<table>`。置き場所より優先します ([テーブルとの対応](#テーブルとの対応)) |
| `title`・`description`・`keywords` | |
| `primary_key` | 1 行を識別する列の並び |
| `licenses`・`sources`・`temporal_coverage`・`spatial_coverage` | データセットと違うときだけ書きます |
| `sql`・`depends_on` | dbt で作らないテーブルの、元の SQL と元のテーブル |
| `columns` | `name`・`title`・`description`・`asset` と、semantic のキー (`entity`・`dimension`・`granularity`) |
| `metrics` | 集計のしかた ([semantic](#semantic)) |
| `queria`・`annotations` | 読み手ごとのキー |

型・NULL・行数は書きません。構造はデータの置き場が持ちます。

`asset: true` は、列の値がその行に属するファイルのパスであることを表します。

## テーブルとの対応

- 既定は置き場所で決めます。`<schema>/<table>.yml` にあるファイルは `<schema>.<table>` を説明します。ルートの直下に置いたファイルは `main` スキーマです
- `table: <schema>.<table>` を書くと、置き場所よりそちらを優先します。ほかの深さに置くときは必須です
- 同じテーブルを 2 つのファイルが説明していると、エラーになります
- テーブルのファイルを dbt の `models/` に置いても、dbt は読みません (`models:` の外のキーを dbt は無視します)

## ガイドと文書

- テーブルのガイドは、テーブルのファイルと同じフォルダの同じ名前の `.md` です (`series.yml` に対して `series.md`)。フロントマターは書きません
- データセットの概要はルートの `README.md` です。スキーマのガイドは `schemas[].guide`、それ以外の文書は `docs` にパスを並べます
- Markdown が相対パスで指すファイル (画像・PDF・ほかの文書) も一緒に送ります。ルートの外を指すリンクはエラー、無いファイルへのリンクは警告で、フォルダへのリンクは扱いません
- ビルドや保守の手順は `CONTRIBUTING.md` に書き、`docs` には並べません

## dbt のプロジェクト

ルートに `dbt_project.yml` があると、tabledoc は `target/manifest.json` (`--manifest` で変更できます) を読みます。先に `dbt compile` (またはビルド) を実行してください。manifest が無いときは警告を出し、テーブルのファイルだけを読みます。

- テーブルは、有効なモデルのうち `materialized` が `table`・`view`・`incremental` のものです。モデルの `schema` と `alias` で名前を決めます。`ephemeral` と無効なモデル、seed・snapshot・テストはテーブルにならないので並べません。説明の無いモデルは `sql` と `depends_on` だけで並べます
- 説明はモデルの yml から取ります。`description` と列の `description` はそのまま、dbt に無いキー (`title`・`primary_key`・`sources`・列の `title`・`asset` など) と `queria` は `config.meta` に書きます
- semantic は列の `entity`・`dimension`・`granularity` と、セマンティックレイヤーの simple の `metrics` から取ります
- `sql` は `compiled_code` です。`depends_on` は DuckDB の構文解析で SQL から読みます。ほかのデータセットのテーブルは `<リポジトリの URL>#<schema>.<table>` と書き、URL は `profiles.yml` (`--profiles`、無ければ `DBT_PROFILES_DIR`、無ければルート) の DuckLake の ATTACH から引きます
- ガイドはモデルの `.sql` の隣の同じ名前の `.md` です (dbt は docs ブロックの無い `.md` を無視します)
- 1 つのテーブルの説明は 1 か所に書きます。テーブルのファイルと dbt の yml の両方に説明があると、エラーになります。dbt の yml に説明が無ければテーブルのファイルを読み、`sql` は dbt から取ります

```yaml
models:
  - name: series
    description: 1 行が 1 系列です。
    config:
      meta:
        title: 系列の一覧
        primary_key: [db, series_code]
    columns:
      - name: db
        description: databases の db と同じ
        dimension: categorical
        config:
          meta: {title: DB 名}
```

dbt で作らないテーブル (Python で作るものなど) は、同じプロジェクトの中でもテーブルのファイルで書きます。

## semantic

列の意味は、dbt-core 1.12 以降のセマンティックレイヤーの書き方 (列に直接書く形) にそろえます。特定の読み手のキーではなく、tabledoc 自身のキーです。

| キー | 値 | 意味 |
| --- | --- | --- |
| `entity` | `{type, name}`、または `type` だけ | 結合キー。`type` は `primary`・`unique`・`foreign`・`natural`。`name` は値の語彙の名前 (`corporate_number`・`lg_code` など) |
| `dimension` | `categorical`・`time`、または `{type, name}` | 絞り込み・グループ分けに使う列 |
| `granularity` | `day`・`month`・`year` など | `dimension: time` の列の細かさ |
| `metrics` (テーブル) | `[{name, agg, expr, description}]` | 集計のしかた。`agg` は `sum`・`max`・`count_distinct` など |

dbt で `metrics` を書くにはセマンティックレイヤー (`semantic_model: true` と time spine) が要ります。セマンティックレイヤーを使わないプロジェクトでも、列の `entity`・`dimension` は書けます。

## 読み手ごとのキー

特定の読み手だけが使うキーは、その読み手の名前の下に書きます。tabledoc は中身を検査せず、`tabledoc.json` の `annotations.<読み手>` にそのまま入れます。

- Queria のキーは `queria:` に書きます。tabledoc が名前を知っている唯一の読み手で、中身は Queria が検査します
- ほかの読み手は `annotations: {<読み手>: {...}}` に書きます

## tabledoc.json

`tabledoc build` が書く 1 つの JSON です。書き手のファイルの内容を 1 つにまとめ、以前の形式は今の形に読み替えて書きます。形は [英語版](../spec.md#tabledocjson) の例と、`schemas/tabledoc/v1.json` を参照してください。

- `source` は Git の作業コピーから取ります。`repository` は `origin` の URL を https に直したもの (認証情報と `.git` を外す)、`commit` は HEAD、`path` はリポジトリのルートから tabledoc.yml のフォルダまでのパス、`dirty` はコミットしていない変更があるかです。Git の外では省きます。受け手は 2 つを比べるときに `source` と `generator` を除きます
- 文書は本文を入れず、パスで参照します。`files` に、本文を送るすべてのファイル (ガイド・README・`docs`・それらが指すファイル) をパス・sha256・大きさ・メディアタイプで並べます。`guide`・`docs`・`schemas[].guide` の値は `files` のパスです
- semantic は書き方によらず `{type, name}` の形にします (`dimension: categorical` は `{"type": "categorical"}`)
- テーブルは `schema`・`name` の順に並べます。同じ入力からは同じバイト列を書きます
- 構造 (型・NULL・行数・ビューかどうか) は入れません

## push

`tabledoc push <URL>` は `target/tabledoc.json` (`--file` で変更できます) を、`--token` か `TABLEDOC_TOKEN` のトークンを `Authorization: Bearer <token>` に載せて送ります。

```
PUT <URL>                                  tabledoc.json (Content-Encoding: gzip)
  ← 409 {"missing": ["<sha256>", …]}       受け手に無いファイル
PUT <クエリを外した URL>/files/<sha256>     ファイルの本文。Content-Type はメディアタイプ
PUT <URL>                                  もう一度。201 は新しい改訂、200 は同じ内容
```

URL にはクエリ (`?version=` など) を付けられます。クエリは tabledoc.json を送るときにだけ付けます。送る前に、各ファイルの sha256 が `tabledoc.json` と同じかを確認します。

## 以前の形式

すべてのデータセットを一度に書き換えずに済むように、tabledoc は置き換える前の形式も読みます。新しく書くのは tabledoc の形式だけです。

- `tabledoc.yml` が無く `queria.yml` (`https://queria.io/schemas/dataset/v1.json`) があれば、それを tabledoc.yml として読みます。最上位の `title_kana`・`themes`・`cover`・`ai_context` は `queria:` の下にあるものとして扱います。`catalogs` は `depends_on` に使い、`tabledoc.json` には入れません
- フロントマターに `$schema: https://queria.io/schemas/table/v1.json` を持つ Markdown は、フロントマターをテーブルのファイル、本文をガイドとして読みます。`table:` で対応を決め、`fields` は `columns`、`published`・`themes`・`ai_context` は `queria:` の下として扱います。ガイドはその Markdown のパスで、送る本文はフロントマターを外したものです
- 列の `semantic: {role, name, agg}` は次のように読み替えます。`role: entity` → `entity: {type: foreign, name}`、その列だけで `primary_key` になっていれば `type: primary`。`role: dimension` → `dimension: categorical`。`role: measure` → テーブルの metrics に `{name: <列名>, agg, expr: <列名>}` (`agg` が無ければ警告)
- 同じフォルダに `tabledoc.yml` と `queria.yml` があるとエラーになります

## $schema とバージョン

- JSON Schema は tabledoc に同梱し、`https://queria-io.github.io/tabledoc/schemas/<種類>/v<n>.json` で配ります。種類は `dataset`・`table`・`tabledoc` (生成する JSON) です
- キーを追加するだけなら同じバージョンのままです。キーの意味を変える・消すときは `v2` にし、tabledoc はしばらく両方を読みます
- 知らない `$schema` のファイルは断り、tabledoc を上げるよう伝えます
- 受け手は `tabledoc.json` の `$schema` で読み方を決めます
