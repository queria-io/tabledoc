---
title: 仕様 (v1)
sidebar:
  label: 仕様
  order: 2
description: tabledoc が読むファイル、その検査、プログラムに返す値を定めます。
---

tabledoc は、人が書くデータセットの説明 (YAML と Markdown、または dbt のプロジェクトの yml) の書き方を定め、検査し、ほかのプログラムのために読むツールです。特定の配信先には依存しません。`tabledoc load` は説明を DuckLake のカタログに書きます。書き手のファイルが正です。

## コマンド

- `tabledoc validate`: 書き手のファイルを検査します
- `tabledoc load`: 検査してから、説明を DuckLake のカタログに書きます ([DuckLake のカタログに書く](#ducklake-のカタログに書く))

エラーがあると終了コード 1 (`--strict` では警告も)、ファイルを読めないときは 2 で終わります。

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

特定の読み手だけが使うキーは、その読み手の名前の下に書きます。tabledoc は中身を検査せず、`annotations.<読み手>` にそのまま入れて返します。

- Queria のキーは `queria:` に書きます。tabledoc が名前を知っている唯一の読み手で、中身は Queria が検査します
- ほかの読み手は `annotations: {<読み手>: {...}}` に書きます

## Python から読む

説明をほかの場所に送るプログラムや、別の形式に変えるプログラムは `tabledoc.read` で読みます。`validate` と同じ検査をして、以前の形式を今の形に読み替えた説明を返します。

```python
import tabledoc

report = tabledoc.Report()
d = tabledoc.read(tabledoc.Options(root), report)  # root: tabledoc.yml のフォルダ
if report.failed:
    print(report.render())
d.dataset   # {"name": "boj", "title": …, "guide": "README.md", "docs": […], "annotations": {…}}
d.schemas   # [{"name": "timeseries", "title": "Time series"}]
d.tables    # [{"schema": "timeseries", "name": "series", "sql": …, "depends_on": […], "guide": …, "columns": […]}]
d.files     # [File(path="README.md", sha256="…", bytes=1234, media_type="text/markdown"), …]
d.source    # {"repository": "https://github.com/…", "commit": "…", "path": "", "dirty": False}
d.catalogs  # {"other": "https://…"}: SQL が読むほかのデータセット (SQL の中の名前 → URL)
d.content(d.files[0])  # そのファイルの中身
```

- `source` は Git の作業コピーから取ります。`repository` は `origin` の URL を https に直したもの (認証情報と `.git` を外す)、`commit` は HEAD、`path` はリポジトリのルートから tabledoc.yml のフォルダまでのパス、`dirty` はコミットしていない変更があるかです。Git の外と `Options(with_source=False)` では None です
- 文書はパスで参照します。`files` に、説明と一緒に送るファイル (ガイド・README・`docs`・それらが指すファイル) をパス・sha256・大きさ・メディアタイプで並べます。`guide`・`docs`・`schemas[].guide` の値は `files` のパスです。`content` はファイルの中身を返します。以前の形式の Markdown のテーブルのファイルでは、フロントマターを外した本文です
- semantic は書き方によらず `{type, name}` の形にします (`dimension: categorical` は `{"type": "categorical"}`)
- テーブルは `schema`・`name` の順に並べ、キーの順も決まっています。同じファイルからは同じ値を返します
- 構造 (型・NULL・行数・ビューかどうか) は入れません

## DuckLake のカタログに書く

`tabledoc load` は `validate` と同じ検査をしてから、説明を [DuckLake](https://ducklake.select) のカタログの `_meta` スキーマのテーブルとして書きます。カタログを読むプログラムは、データと一緒に説明も SQL で読めます。

```bash
tabledoc load --ducklake work.sqlite --data-path data/ --out .fdl/pack
```

- `--ducklake`: カタログ (既定は `FDL_WORKING`)。`--data-path`: 新しいデータファイルを置く場所 (既定は `FDL_DATA_PATH`、無ければ `fdl clone` がカタログの横に記録したフォルダ)
- `--out`: `fdl commit` に渡すフォルダも書きます。`dataset.json` (`--dataset` に渡す主キーと asset の列) と `assets/` (`--assets` に渡す `_meta.files` のファイル) です。`--assets <フォルダ>` を付けると、その下のファイルも `assets/` にリンクします。フォルダは空か、前の `load` が書いたものでなければなりません
- `--unlisted`: 説明の無いテーブルとビューにも `_meta.tables` の行を作り、`published` を false にします
- 説明や主キーにあってカタログに無いテーブルと列はエラーです。名前は DuckDB と同じく大文字と小文字を区別せずに照合します
- `_meta` の列の型に合わない値はエラーです。`YYYY-MM-DD` 以外の `issued` や、`queria:` の下の型の違うキー (文字列で書いた `themes` など) が該当します
- エラー (`--strict` では警告も) があると何も書きません

| テーブル | キー | 1 行の単位 |
| --- | --- | --- |
| `_meta.dataset` | | データセット: `title`・`description`・`language`・`keywords`・`homepage`・`issued`・`update_frequency`・`licenses`・`sources`・`contributors`・`temporal_coverage`・`spatial_coverage` |
| `_meta.schemas` | `schema` | スキーマ: `title`・`description` |
| `_meta.tables` | `schema`・`name` | テーブルとビュー: `title`・`description`・`keywords`・`licenses`・`sources`・`temporal_coverage`・`spatial_coverage`・`materialized`・`sql`・`depends_on`・`source_path` |
| `_meta.columns` | `schema`・`table`・`name` | 説明のある列: `title`・`description`・`entity` (結合キーの名前) |
| `_meta.files` | `path` | ガイドと文書: `sha256`・`bytes`・`media_type`・`kind` (`guide` か `doc`)・`schema`・`table` (ガイドの対象)・`position` (`docs` の順番)・`title` |

- `queria:` のキーのうち Queria がカタログから読むものも列にします。`_meta.dataset` の `title_kana`・`themes`・`cover`・`ai_context` と、`_meta.tables` の `published`・`themes`・`ai_context` です。読み手は知らない列を無視します
- `licenses` は `{id, spdx, url, title, commercial_use, share_alike, attribution_required}` のリストです。文字列で書いたライセンスは `{id}` になります
- ファイルの中身はカタログに入れません。`_meta.files.sha256` は asset の列で、FDL では `fdl commit --assets` が中身ごとにファイルをアップロードします
- テーブル・ビュー・列の説明は DuckDB のコメント (`COMMENT ON`) にも書くので、`DESCRIBE` や `duckdb_tables()` でも読めます。ビューの列には書きません
- `_meta` のテーブルは毎回 1 つのトランザクションで作り直します。dbt のビルドが無いとき (説明に `sql` が無いとき) は、各テーブルの `sql` と `depends_on` をカタログの `_meta` から引き継ぎます

## 以前の形式

すべてのデータセットを一度に書き換えずに済むように、tabledoc は置き換える前の形式も読みます。新しく書くのは tabledoc の形式だけです。

- `tabledoc.yml` が無く `queria.yml` (`https://queria.io/schemas/dataset/v1.json`) があれば、それを tabledoc.yml として読みます。最上位の `title_kana`・`themes`・`cover`・`ai_context` は `queria:` の下にあるものとして扱います。`catalogs` は `depends_on` に使い、`catalogs` として返します
- フロントマターに `$schema: https://queria.io/schemas/table/v1.json` を持つ Markdown は、フロントマターをテーブルのファイル、本文をガイドとして読みます。`table:` で対応を決め、`fields` は `columns`、`published`・`themes`・`ai_context` は `queria:` の下として扱います。ガイドはその Markdown のパスで、送る本文はフロントマターを外したものです
- 列の `semantic: {role, name, agg}` は次のように読み替えます。`role: entity` → `entity: {type: foreign, name}`、その列だけで `primary_key` になっていれば `type: primary`。`role: dimension` → `dimension: categorical`。`role: measure` → テーブルの metrics に `{name: <列名>, agg, expr: <列名>}` (`agg` が無ければ警告)
- 同じフォルダに `tabledoc.yml` と `queria.yml` があるとエラーになります

## $schema とバージョン

- JSON Schema は tabledoc に同梱し、`https://queria-io.github.io/tabledoc/schemas/<種類>/v<n>.json` で配ります。種類は `dataset` と `table` です
- キーを追加するだけなら同じバージョンのままです。キーの意味を変える・消すときは `v2` にし、tabledoc はしばらく両方を読みます
- 知らない `$schema` のファイルは断り、tabledoc を上げるよう伝えます
