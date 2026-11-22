---
title: 仕様 (v1)
sidebar:
  label: 仕様
  order: 2
description: tabledoc が読むファイル、その検査、プログラムに返す値を定めます。
---

tabledoc は、人が書くデータセットの説明 (YAML と Markdown、または dbt のプロジェクトの yml) の書き方を定め、検査し、ほかのプログラムのために読むツールです。特定の配信先には依存しません。`tabledoc load` は説明を DuckLake のカタログに、1 つのスキーマ (既定は `_tabledoc`) の普通のテーブルとして書き、`tabledoc dump` はそこからファイルを書き戻します。書き手のファイルが正です。

## コマンド

- `tabledoc validate`: 書き手のファイルを検査します
- `tabledoc load`: 検査してから、説明を DuckLake のカタログに書きます ([DuckLake のカタログに書く](#ducklake-のカタログに書く))
- `tabledoc dump`: カタログが持つ説明のファイルを書きます ([カタログからファイルを書く](#カタログからファイルを書く))

エラーがあると終了コード 1 (`--strict` では警告も)、ファイルやカタログを読み書きできないときは 2 で終わります。

## ファイル

パスは `tabledoc.yml` のあるフォルダ (以下ルート) からの相対パスです。

```
tabledoc.yml              データセット (名前は固定)
README.md                 データセットの概要 (任意)
<schema>/<table>.yml      テーブル
<schema>/<table>.md       テーブルのガイド (任意。<schema>/<table>/README.md でも可)
<schema>/README.md        スキーマのガイド (任意)
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
topics: [日本銀行, 金利, 物価]
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
  title_kana: ニチギンジケイレツトウケイ
```

| キー | 必須 | 内容 |
| --- | --- | --- |
| `$schema` | 必須 | 書式とバージョン |
| `name` | 必須 | データセットの名前。`^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$` |
| `schema` | | `tabledoc load` が説明を書くスキーマ。既定は `_tabledoc` |
| `title`・`description`・`topics`・`homepage`・`language`・`issued`・`update_frequency` | | `language` は BCP 47 のタグ、`issued` は `YYYY-MM-DD` |
| `licenses`・`sources`・`contributors`・`temporal_coverage`・`spatial_coverage` | | テーブルのファイルに書くと、そのテーブルだけの値になります |
| `schemas` | | `name`・`title`・`description`・`guide` (スキーマのガイドのパス。省くと、あれば `<name>/README.md`)・`docs` (スキーマのほかの文書) |
| `docs` | | データセットのほかの文書のパス |
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
| `title`・`description`・`topics` | `topics` は GitHub のリポジトリのトピックと同じものです。以前の名前の `keywords` も `topics` として読みます。Queria が読むので、`queria:` の `topics` として書き出します |
| `primary_key` | 1 行を識別する列の並び |
| `licenses`・`sources`・`temporal_coverage`・`spatial_coverage` | データセットと違うときだけ書きます |
| `sql`・`depends_on` | dbt で作らないテーブルの、元の SQL と元のテーブル |
| `docs` | テーブルのほかの文書のパス |
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

- テーブルのガイドは、テーブルのファイルと同じフォルダの同じ名前の `.md` (`series.yml` に対して `series.md`) か、その名前のフォルダの `README.md` (`series/README.md`) です。フロントマターは書きません
- データセットの概要はルートの `README.md` です。スキーマのガイドは `schemas[].guide`、無ければ `<schema>/README.md` です
- ほかの文書は `docs` にパスを並べます。データセットの文書は `tabledoc.yml`、スキーマの文書は `schemas[].docs`、テーブルの文書はテーブルのファイルに書きます。パスはルートからの相対パスです
- Markdown が相対パスで指すファイル (画像・PDF・ほかの文書) も一緒に送ります。ルートの外を指すリンクはエラー、無いファイルへのリンクは警告で、フォルダへのリンクは扱いません
- ビルドや保守の手順は `CONTRIBUTING.md` に書き、`docs` には並べません

### データセットの中のパス

データセットの中では、フォルダ 1 つが説明の対象 1 つです。ルートはデータセット、`<schema>/` はスキーマ、`<schema>/<table>/` はテーブルです。フォルダの `README.md` がその対象の説明で、同じフォルダのほかの Markdown がその対象の文書です。書き手が手元のどこに置いても、tabledoc はファイルを次のパスに置きます。

| 書いたもの | データセットの中のパス |
| --- | --- |
| `README.md` | `README.md` |
| `docs` の項目 | `<ファイル名>` |
| スキーマのガイド | `<schema>/README.md` |
| `schemas[].docs` の項目 | `<schema>/<ファイル名>` |
| テーブルのガイド | `<schema>/<table>/README.md` |
| テーブルの `docs` の項目 | `<schema>/<table>/<ファイル名>` |
| 文書が指すファイル | ルートからのパスのまま |

- Markdown の文書の中の相対リンクのうち、別のパスに置いたファイルを指すものは、新しいパスを指すように書き換えます。`sha256` と `bytes` は書き換えた後の文書の値です
- データセットの中の同じパスに 2 つのファイルを置くことになるときはエラーです

## dbt のプロジェクト

ルートに `dbt_project.yml` があると、tabledoc は `target/manifest.json` (`--manifest` で変更できます) を読みます。先に `dbt compile` (またはビルド) を実行してください。manifest が無いときは警告を出し、テーブルのファイルだけを読みます。カタログに dbt で作ったテーブル (`source_path` のあるテーブル) があるときは、`load` はその SQL を引き継ぐので、警告ではなく情報として出します。

- テーブルは、有効なモデルのうち `materialized` が `table`・`view`・`incremental` のものです。モデルの `schema` と `alias` で名前を決めます。`ephemeral` と無効なモデル、seed・snapshot・テストはテーブルにならないので並べません。説明の無いモデルは dbt が埋める値 (`materialized`・`sql`・`depends_on`・`source_path`) だけで並べます
- 説明はモデルの yml から取ります。`description` と列の `description` はそのまま、dbt に無いキー (`title`・`primary_key`・`sources`・列の `title`・`asset` など) と `queria` は `config.meta` に書きます
- semantic は列の `entity`・`dimension`・`granularity` と、セマンティックレイヤーの simple の `metrics` から取ります
- `materialized` はモデルの materialization、`source_path` は `original_file_path`、`sql` は `compiled_code` です。`depends_on` は DuckDB の構文解析で SQL から読みます。ほかのデータセットのテーブルは `<リポジトリの URL>#<schema>.<table>` と書き、URL は `profiles.yml` (`--profiles`、無ければ `DBT_PROFILES_DIR`、無ければルート) の DuckLake の ATTACH から引きます
- ガイドはモデルの `.sql` の隣の同じ名前の `.md` か、その名前のフォルダの `README.md` です (dbt は docs ブロックの無い `.md` を無視します)。ほかの文書は `config.meta` の `docs` に書きます
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
d.dataset   # {"name": "boj", "title": …, "guide": "README.md", "docs": ["methodology.md"], "annotations": {…}}
d.schemas   # [{"name": "timeseries", "title": "Time series"}]
d.tables    # [{"schema": "timeseries", "name": "series", "sql": …, "depends_on": […], "guide": …, "columns": […]}]
d.files     # [File(path="README.md", sha256="…", bytes=1234, media_type="text/markdown", local="README.md"), …]
d.source    # {"repository": "https://github.com/…", "commit": "…", "path": "", "dirty": False}
d.catalogs  # {"other": "https://…"}: SQL が読むほかのデータセット (SQL の中の名前 → URL)
d.content(d.files[0])  # そのファイルの中身
```

- `source` は Git の作業コピーから取ります。`repository` は `origin` の URL を https に直したもの (認証情報と `.git` を外す)、`commit` は HEAD、`path` はリポジトリのルートから tabledoc.yml のフォルダまでのパス、`dirty` はコミットしていない変更があるかです。Git の外と `Options(with_source=False)` では None です
- 文書はパスで参照します。`files` に、説明と一緒に送るファイル (ガイド・README・`docs`・それらが指すファイル) を[データセットの中のパス](#データセットの中のパス)・sha256・大きさ・メディアタイプと、ルートからのパス `local` で並べます。`guide`・`docs`・`schemas[].guide`・`schemas[].docs` の値は `files` のパスです。`content` はデータセットに入れる中身を返します。Markdown の文書はリンクを書き換えた本文、以前の形式の Markdown のテーブルのファイルはフロントマターを外した本文です
- semantic は書き方によらず `{type, name}` の形にします (`dimension: categorical` は `{"type": "categorical"}`)
- テーブルは `schema`・`name` の順に並べ、キーの順も決まっています。同じファイルからは同じ値を返します
- 構造 (型・NULL・行数・ビューかどうか) は入れません

## DuckLake のカタログに書く

`tabledoc load` は `validate` と同じ検査をしてから、説明を [DuckLake](https://ducklake.select) のカタログの 1 つのスキーマに、普通のテーブルとして書きます。スキーマは `tabledoc.yml` の `schema` か `--schema` で指定し、指定が無ければ `_tabledoc` です。テーブルはデータと一緒にバージョン管理され、カタログを読むプログラムは説明も SQL で読めます。fdl では、カタログは `fdl clone` が作る作業用メタデータで、`fdl commit` でバージョンにします。

```bash
tabledoc load --ducklake work.sqlite --out build/assets
fdl commit work.sqlite -m "..." --assets build/assets
```

- `--ducklake`: カタログ (既定は `FDL_WORKING`)。`--data-path`: 新しいデータファイルを置く場所 (既定は `FDL_DATA_PATH`、無ければ `fdl clone` がカタログの横に記録したフォルダ)
- `--schema`: 書くスキーマ (既定は `tabledoc.yml` の `schema`、無ければ `_tabledoc`)。Queria は `_queria` を読みます。Queria で公開するデータセットでは `--schema _queria` (か `schema: _queria`) を指定します
- `--out`: `fdl commit --assets` に渡すフォルダも書きます。`files` テーブルの各ファイルを `files/<path>` に置きます。`--assets <フォルダ>` を付けると、その下のファイル (ビルドが作った asset の列のファイル) を `data/` にリンクします。フォルダは空か前の `load` が書いたもので、fdl だけが書く `.fdl/` の外でなければなりません
- `--unlisted`: 説明の無いテーブルとビューにも `tables` の行を作り、`published` を false にします
- 説明や主キーにあってカタログに無いテーブルと列、`varchar` でない `asset` の列はエラーです。名前は DuckDB と同じく大文字と小文字を区別せずに照合し、カタログの表記で書きます
- 列に入らない値 (`YYYY-MM-DD` 以外の `issued` など) はエラーです
- エラー (`--strict` では警告も) があると何も書きません

| テーブル | 主キー | 元の値 |
| --- | --- | --- |
| `dataset` | `id` (常に `dataset`) | `tabledoc.yml` の `title`・`description`・`language`・`homepage`・`issued`・`update_frequency`・`licenses`・`sources`・`contributors`・`temporal_coverage`・`spatial_coverage`・`topics`、`queria:` の `title_kana`・`cover`・`ai_context` |
| `schemas` | `schema` | `title` か `description` のある `schemas[]` |
| `tables` | `schema`・`name` | 説明のあるテーブルとビュー: `title`・`description`・`licenses`・`sources`・`temporal_coverage`・`spatial_coverage`・`topics`・`sql`・`depends_on`・dbt の `materialized` と `source_path`、`queria:` の `published`・`ai_context` |
| `columns` | `schema`・`table`・`name` | `title`・`description`・`entity` のどれかがある列。`entity` は entity の `name` (`lg_code` などのコード体系) です |
| `files` | `path` | [データセットの中のファイル](#データセットの中のパス): `path`・`sha256`・`bytes`・`media_type` |

- `topics` (以前の名前の `keywords`) は、`queria:` に `topics` が無ければ書きます。`queria:` の `themes` は書きません
- `licenses` は `{id, spdx, url, title, commercial_use, share_alike, attribution_required}` のリストです。文字列で書いたライセンスは `{id}` になります
- ビューの行には `sql` と `depends_on` を書きません。ビューの SQL はメタデータが持ちます
- `annotations:` のうち Queria 以外の読み手のキーは書きません
- ファイルの中身はカタログに入れません。`files.sha256` に各ファイルの sha256 を書き、`fdl commit --assets` が中身ごとにファイルをアップロードします
- 行は主キーごとに追加・更新・削除するので、`load` は値の違うセルだけを変えます。dbt のビルドが無いとき (説明に `sql` が無いとき) は、各テーブルの `sql`・`depends_on`・`materialized`・`source_path` をカタログから引き継ぎます
- 主キーと asset の列はこれらのテーブルに書きません。FDL が自分の宣言として受け取ります
- コメント (`COMMENT ON`) は書きません

## カタログからファイルを書く

`tabledoc dump` は、カタログが持つ説明のファイルを書きます。`tabledoc.yml`、説明のあるテーブルごとのテーブルのファイル、`files` テーブルの各ファイル (そのパスに) です。書いたファイルを `tabledoc load` で読むと、同じテーブルになります。

```bash
tabledoc dump --ducklake work.sqlite --out description/
```

- `--ducklake`: カタログ (既定は `FDL_WORKING`)。`--schema`: 説明のあるスキーマ (既定は `_tabledoc`)。`--out`: 書くフォルダ (既定は今のフォルダ)。`.fdl/` の外でなければなりません
- `--files`: `files` テーブルのファイルの置き場所。`<files>/<sha256>` で読みます。フォルダか http(s) の URL です。既定は、`fdl clone` がカタログの横に記録したリポジトリの `assets/` です。各ファイルは sha256 で照合します
- `--name`: `tabledoc.yml` の `name`。既定はリポジトリの URL の最後の部分です
- フォルダに同じファイルがあると、`--force` を付けない限り何も書きません
- テーブルのファイルは `<schema>/<table>.yml`、ガイドは `<schema>/<table>/README.md` に書きます。フォルダの `README.md` 以外の Markdown は、そのフォルダの `docs` に並べます
- テーブルに無いものは書きません。主キー、asset の列、entity の種類 (`foreign` と書きます)・dimension・granularity・metrics、ほかの読み手のキーと、dbt の `profiles.yml` から取る SQL が読むほかのデータセットです。`--unlisted` だけが書いたテーブルにはテーブルのファイルを作りません。`sql` と `depends_on` は `source_path` の無いテーブル (dbt で作らないテーブル) にだけ書きます

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
