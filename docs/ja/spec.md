---
title: 仕様 (v1)
sidebar:
  label: 仕様
  order: 2
description: データセットを説明する語彙と、その 2 つの表現 (ファイルとテーブル)、tabledoc の CLI の動作を定めます。
---

tabledoc は、データセットを人に向けて説明するための規約です。各テーブルと列の意味、ライセンス・出典・作成者、一緒に読むガイドを書きます。同じ語彙を 2 つの形で表します。

- 書き手が書くファイル: YAML と Markdown、または dbt のプロジェクトの yml ([ファイル](#ファイル))
- データと同じデータベースに置くテーブル: スキーマ `_tabledoc` のテーブル ([テーブル](#テーブル))

プログラムはどちらの形も読めて、2 つは同じ説明を持ちます。テーブルの列は文字列・真偽値・整数だけなので、SQL のスキーマを持つデータベースならどこにでも置けます。たとえば DuckLake・Iceberg・PostgreSQL・BigQuery です。tabledoc は履歴を持ちません。テーブルを置いたカタログがデータと一緒にバージョン管理します (DuckLake のスナップショット、FDL のバージョン)。カタログにその仕組みが無いときは、ファイルを Git で管理します。

`tabledoc` コマンドは参照実装です。ファイルを検査し、DuckLake のカタログのテーブルに書き (`tabledoc load`)、テーブルからファイルを書き戻し (`tabledoc dump`)、AI アシスタントや人が読む Markdown を書き出します (`tabledoc export --markdown`)。

## コマンド

- `tabledoc validate`: 書き手のファイルを検査します
- `tabledoc load`: 検査してから、説明を DuckLake のカタログのテーブルに書きます ([DuckLake のカタログに書く](#ducklake-のカタログに書く))
- `tabledoc dump`: カタログが持つ説明のファイルを書きます ([カタログからファイルを書く](#カタログからファイルを書く))
- `tabledoc export --markdown`: 検査してから、テーブルごとに 1 つの Markdown として書き出します ([AI のために Markdown を書き出す](#ai-のために-markdown-を書き出す))

エラーがあると終了コード 1 (`--strict` では警告も)、ファイルやカタログを読み書きできないときは 2 で終わります。

## ファイル

パスは `tabledoc.yml` のあるフォルダ (以下ルート) からの相対パスです。

```
tabledoc.yml              データセット (名前は固定)
README.md                 データセットの概要 (任意)
<schema>/<table>.tabledoc.yml   テーブル
<schema>/<table>.md             テーブルのガイド (任意)
```

1 つのテーブルの説明を 1 つのファイルに書き、どのテーブルの説明かはファイルの名前と置き場所で決めます。ほかの文書は `documents` にパスを並べるので ([ガイドと文書](#ガイドと文書))、ルートの中のどこに置いてもかまいません。

dbt のプロジェクトでは、テーブルのファイルをモデルの `.sql` の隣に置きます。`<model>.sql` の隣の `<model>.tabledoc.yml` と `<model>.md` です。dbt の yml にはテストなどビルドに要るものだけを書けます ([dbt のプロジェクト](#dbt-のプロジェクト))。

`.` で始まるフォルダと、`target/`・`dbt_packages/`・`node_modules/`・`.venv/` は読みません。

## tabledoc.yml

データセット 1 つの説明です。

```yaml
$schema: https://tabledoc.queria.io/schemas/dataset/v1.json
name: boj
title: 日本銀行 時系列統計
title_reading: ニチギンジケイレツトウケイ
description: 日本銀行の時系列統計データ検索サイトの全ての統計です。
language: ja
topics: [日本銀行, 金利, 物価]
synonyms: [日銀統計]
homepage: https://github.com/queria-io/dataset-boj
update_frequency: irregular
licenses:
  - id: boj-copyright
    title: 日本銀行 著作権・免責事項
    url: https://www.boj.or.jp/about/copyright.htm
sources:
  - id: search-site
    title: 日本銀行 時系列統計データ検索サイト
    url: https://www.stat-search.boj.or.jp/
contributors:
  - id: boj
    title: 日本銀行
    url: https://www.boj.or.jp/
    roles: [rightsHolder]
spatial_coverage: [JP]
image: docs/cover.png
schemas:
  - name: timeseries
    title: 時系列統計
documents:
  - docs/methodology.md
```

| キー | 必須 | 内容 |
| --- | --- | --- |
| `$schema` | 必須 | 書式とバージョン |
| `name` | 必須 | データセットの名前。`^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$` |
| `title`・`title_reading`・`description`・`topics`・`synonyms`・`homepage`・`language`・`issued`・`update_frequency` | | `title_reading` はタイトルの読み (日本語ならカタカナなど) です。`synonyms` は検索に使う別名です。`language` は BCP 47 のタグで、言語を付けずに書いた文字列の言語です ([言語](#言語))。`issued` は `YYYY-MM-DD` です。`update_frequency` は `continuous`・`daily`・`weekly`・`monthly`・`quarterly`・`yearly`・`irregular` のどれかです |
| `repository` | | データセットのソースコードのリポジトリの URL。例: `https://github.com/queria-io/dataset-boj`。省くと `tabledoc load` は Git の `origin` を使います |
| `licenses`・`sources`・`contributors`・`temporal_coverage`・`spatial_coverage` | | [ライセンス・出典・作成者](#ライセンス出典作成者)。`licenses`・`sources` と期間・地域は、テーブルのファイルに書くとそのテーブルだけの値になります |
| `image` | | データセットを表す画像のパス。文書と一緒に送り、ルートからのパスのまま置きます |
| `schemas` | | `name`・`title`・`title_reading`・`description`・`topics`・`synonyms`・`documents` (スキーマの文書) |
| `documents` | | データセットの文書のパス |
| `annotations` | | ほかの読み手のキー。読み手の名前ごとに書きます ([ほかの読み手のキー](#ほかの読み手のキー)) |

## テーブルのファイル

テーブル 1 つの説明です。名前が `<table>.tabledoc.yml` で、`$schema` が `https://tabledoc.queria.io/schemas/table/v1.json` の YAML をテーブルのファイルとして読みます。ほかの YAML (dbt の yml など) はテーブルのファイルとして読みません。キーは dbt の `models:` の 1 項目と同じで、dbt に無いキー (`title`・`primary_key`・`sources` など) は同じ階層に並べます。

```yaml
$schema: https://tabledoc.queria.io/schemas/table/v1.json
name: series
title: 系列の一覧
description: |-
  検索サイトの全 DB の系列の一覧です。1 行が 1 系列です。
primary_key: [db, series_code]
sources: [search-site]
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
| `name` | テーブル名。書くときはファイル名と同じにします ([テーブルとの対応](#テーブルとの対応)) |
| `title`・`title_reading`・`description`・`topics`・`synonyms` | `topics` は GitHub のリポジトリのトピックと同じものです |
| `hidden` | `true` にすると、一覧と検索に出しません。ほかのテーブルが読むだけのテーブルなどに使います。既定は `false` です |
| `primary_key` | 1 行を識別する列の並び |
| `licenses`・`sources`・`temporal_coverage`・`spatial_coverage` | データセットと違うときだけ書きます |
| `sql`・`depends_on` | dbt で作らないテーブルの、元の SQL と元のテーブル |
| `documents` | テーブルの文書のパス |
| `columns` | `name`・`title`・`title_reading`・`description`・`topics`・`synonyms`・`asset` と、semantic のキー (`entity`・`dimension`・`granularity`) |
| `metrics` | 集計のしかた ([semantic](#semantic)) |
| `annotations` | ほかの読み手のキー |

型・NULL・行数は書きません。構造はデータの置き場が持ちます。

`asset: true` は、列の値がその行に属するファイルのパスであることを表します。

## テーブルとの対応

- 名前と置き場所で決めます。`<schema>/<table>.tabledoc.yml` は `<schema>.<table>` を説明します。ルートの直下に置いたファイルは `main` スキーマです
- dbt のプロジェクトでは、モデルのファイル (`<model>.sql`、Python のモデルは `<model>.py`) の隣の `<model>.tabledoc.yml` がそのモデルのテーブルを説明します。テーブル名はモデルの `schema` と `alias` で決まります。隣にモデルの無いテーブルのファイルはエラーです
- それ以外の場所に置いたテーブルのファイルと、ファイル名と違う `name` はエラーです
- dbt はモデルのパスの下の yml をすべて構文解析し、テーブルのファイルの `sources` を dbt の `sources:` として読もうとします。テーブルのファイルを置く dbt のプロジェクトは、`.dbtignore` に `*.tabledoc.yml` を書きます。書いていないと tabledoc はエラーにします

## ライセンス・出典・作成者

ライセンス・出典・作成者には、それぞれ `id` を付けます。短く、変えず、データセットの中で重複しない値にします。テーブルは `id` で参照するので、タイトルを直しても参照する側は変わりません。

```yaml
licenses:
  - CC-BY-4.0                       # id だけ
  - id: boj-copyright
    title: 日本銀行 著作権・免責事項
    url: https://www.boj.or.jp/about/copyright.htm
sources:
  - id: search-site
    title: 日本銀行 時系列統計データ検索サイト
    url: https://www.stat-search.boj.or.jp/
```

- 1 つの項目は `tabledoc.yml` かいずれかのテーブルのファイルに 1 回だけ全部書き、ほかの場所では `id` だけを書きます (`sources: [search-site]`)
- 同じ `id` の項目とキーがすべて一致する項目 (`{id, title, url}` に対する `{id, url}` など) は、その項目を参照します。同じ `id` でキーの値が違う項目を書くとエラーです
- `id` だけを書いたライセンスで、どこにも定義が無いものは、その `id` (`CC-BY-4.0` などの SPDX の識別子) として扱います。SPDX の識別子があるライセンスは、それを `id` にします。どこにも定義の無い出典の `id` はエラーです
- ライセンスは `{id, url, title, commercial_use, share_alike, attribution_required}`、出典は `{id, title, url}`、作成者は `{id, title, url, roles}` です。作成者はデータセットにだけ書きます

## 言語

人が読む文字列は、複数の言語で書けます。値を BCP 47 のタグから文字列への対応で書くか、文字列だけを書きます。文字列だけのときは、データセットの `language` の言語として読みます。

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

- tabledoc のキーのうち、値が文字列か文字列の一覧のものは、どちらの形でも書けます。たとえば `title`・`title_reading`・`description`・`topics`・`synonyms`・`homepage` と、ライセンス・出典・作成者の `title`・`url` です。一覧はタグから一覧への対応にします
- 何かを指す値と、決まった語彙から選ぶ値は、値を 1 つだけ持ちます。`name`・`table`・`repository`・`primary_key`・`entity`・`language`・`$schema`・`issued`・`update_frequency`・`dimension`・`granularity`・`agg`・`expr`・`sql`・`depends_on`・`id`・`roles`・`hidden`・`image`・`spatial_coverage`・`temporal_coverage` と、`documents` のパスです。言語ごとに変えると、同じテーブル・列・ファイルを指せなくなるためです
- テーブルには `title`・`title_reading`・`description`・`topics`・`synonyms` をすべての言語で書きます。ほかの文字列 (`homepage`、ライセンス・出典・作成者、metric の `description`) は `language` の言語の値だけを書き、複数の言語で書いたときは警告を出します
- `annotations:` の下のキーは、それぞれの読み手が決めます
- タグは BCP 47 として検査します。文字列が 1 つも無い対応はエラーです
- dbt のプロジェクトの yml では、`description` は文字列だけで、`language` の言語として読みます。dbt はそこに対応を受け付けません
- `tabledoc.read` はこれらの値を常に対応で返します。文字列だけの値は `{<language>: 文字列}`、`language` が無ければ `{und: 文字列}` になります

## ガイドと文書

- 文書は `documents` にパスを並べます。データセットの文書は `tabledoc.yml`、スキーマの文書は `schemas[].documents`、テーブルの文書はテーブルのファイルに書きます。パスはルートからの相対パスで、ファイルはルートの中のどこに置いてもかまいません
- ファイル名が `README.md` の文書は、並べた先の対象の説明 (ガイド) です。ほかの文書はファイル名のままです
- 次の 2 つは並べなくても文書になります。ルートの `README.md` はデータセットの説明、テーブルのファイルの隣の同じ名前の `.md` (`series.tabledoc.yml`、dbt のプロジェクトでは `series.sql` に対して `series.md`) はそのテーブルのガイドです
- 1 つの対象にガイドが 2 つあるとエラーです (テーブルの `series.md` と、`documents` に並べた `README.md` など)
- スキーマのフォルダや `<schema>/<table>/` の `README.md` で、どの `documents` にも並べていないものは読まず、警告を出します
- 文書にフロントマターは書きません
- Markdown が相対パスで指すファイル (画像・PDF・ほかの文書) も一緒に送ります。ルートの外を指すリンクはエラー、無いファイルへのリンクは警告で、フォルダへのリンクは扱いません
- ビルドや保守の手順は `CONTRIBUTING.md` に書き、`documents` には並べません

### データセットの中のパス

データセットの中では、フォルダ 1 つが説明の対象 1 つです。ルートはデータセット、`<schema>/` はスキーマ、`<schema>/<table>/` はテーブルです。フォルダの `README.md` がその対象の説明で、同じフォルダのほかのファイルがその対象の文書です。書き手が手元のどこに置いても、tabledoc はファイルを次のパスに置きます。

| 書いたもの | データセットの中のパス |
| --- | --- |
| データセットの `documents` の項目 | `<ファイル名>` |
| `schemas[].documents` の項目 | `<schema>/<ファイル名>` |
| テーブルの `documents` の項目 | `<schema>/<table>/<ファイル名>` |
| テーブルのガイド (テーブルのファイルかモデルの隣) | `<schema>/<table>/README.md` |
| 文書が指すファイル | ルートからのパスのまま |

- Markdown の文書の中の相対リンクのうち、別のパスに置いたファイルを指すものは、新しいパスを指すように書き換えます。`sha256` と `bytes` は書き換えた後の文書の値です
- データセットの中の同じパスに 2 つのファイルを置くことになるときはエラーです。1 つのファイルをデータセットの中の 2 つのパスに置くことになるとき (2 つのテーブルの `documents` に同じ文書を書いたときなど) もエラーです

## dbt のプロジェクト

ルートに `dbt_project.yml` があると、tabledoc は `target/manifest.json` (`--manifest` で変更できます) を読みます。先に `dbt compile` (またはビルド) を実行してください。manifest が無いときは警告を出し、テーブルのファイルだけを読みます。カタログに dbt で作ったテーブル (`source_path` のあるテーブル) があり、説明に `sql` が無く、そのテーブルをすべて説明しているときは、`load` はその SQL を引き継ぐので、警告ではなく情報として出します。

- テーブルは、有効なモデルのうち `materialized` が `table`・`view`・`incremental` のものです。モデルの `schema` と `alias` で名前を決めます。`ephemeral` と無効なモデル、seed・snapshot・テストはテーブルにならないので並べません。説明の無いモデルは dbt が埋める値 (`materialized`・`sql`・`depends_on`・`source_path`) だけで並べます
- dbt にキーがあるものは dbt から読みます。モデルと列の `description`、`constraints` の主キー (`type: primary_key`。モデルか 1 つの列に書いたもの)、列の `entity` (その `name`)・`dimension` (その `type`)・`granularity` とセマンティックレイヤーの simple の `metrics` です
- dbt にキーが無いもの (`title`・`title_reading`・`topics`・`synonyms`・`hidden`・`sources`・`licenses`・`documents`・列の `title` と `asset` など) は、2 つの場所のどちらかに書きます。dbt の yml のモデルと列の `config.meta` か、モデルの `.sql` の隣のテーブルのファイル `<model>.tabledoc.yml` です。テーブルのファイルに書くと、テーブルごとの説明が 1 つのファイルにまとまり、dbt の yml はビルドのことだけになります。`config.meta` は、すでにそこに書いているチームのために読みます
- dbt のキー・`config.meta`・テーブルのファイルは、キーごとに (列はさらに列ごとに) 合わせて読みます。同じキーが 2 か所にあるとエラーです。dbt の空の `description` は書いていないものとして扱います。dbt の `constraints` があるときに `config.meta` やテーブルのファイルに `primary_key` を書いても、エラーです
- 説明を書き換えるプログラムは、そのキーが今ある場所に書きます。まだどこにも無いキーはテーブルのファイルに書き、dbt の yml は書き換えません
- `materialized` はモデルの materialization、`source_path` は `original_file_path`、`sql` は `compiled_code` です。`depends_on` は DuckDB の構文解析で SQL から読みます。ほかのデータセットのテーブルは `<dataset>.<schema>.<table>` と書きます。`<dataset>` は SQL がそのデータセットを ATTACH した名前で、URL は `profiles.yml` (`--profiles`、無ければ `DBT_PROFILES_DIR`、無ければルート) の DuckLake の ATTACH から引きます
- ガイドはモデルの `.sql` の隣の同じ名前の `.md` (dbt は docs ブロックの無い `.md` を無視します) か、テーブルの `documents` に並べた `README.md` です

```yaml
models:
  - name: series
    description: 1 行が 1 系列です。
    config:
      meta:
        title: 系列の一覧
    constraints:
      - type: primary_key
        columns: [db, series_code]
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
| `entity` | コード体系の名前 (`corporate_number`・`city` など) | 列が識別子であることを示します。値がそのコード体系から取られているので、同じコード体系を書いたほかのテーブルやデータセットの列と結合できます。行を識別するかどうかは主キーで示します |
| `dimension` | `categorical` か `time` | 絞り込み・グループ分けに使う列 |
| `granularity` | `day`・`month`・`year` など | `dimension: time` の列の細かさ |
| `metrics` (テーブル) | `[{name, agg, expr, description}]` | 集計のしかた。`agg` は `sum`・`max`・`count_distinct` など |

dbt で `metrics` を書くにはセマンティックレイヤー (`semantic_model: true` と time spine) が要ります。セマンティックレイヤーを使わないプロジェクトでも、列の `entity`・`dimension` は書けます。

## ほかの読み手のキー

特定の読み手だけが使うキーは、`tabledoc.yml`・テーブルのファイル・列の `annotations: {<読み手>: {...}}` に書きます。tabledoc は中身を検査せず、書いたとおりに返し、テーブルには書きません。どの読み手も使えるキーは、tabledoc の語彙に入れます。

## Python から読む

説明をほかの場所に送るプログラムや、別の形式に変えるプログラムは `tabledoc.read` で読みます。`validate` と同じ検査をして、以前の形式を今の形に読み替えた説明を返します。

```python
import tabledoc

report = tabledoc.Report()
d = tabledoc.read(tabledoc.Options(root), report)  # root: tabledoc.yml のフォルダ
if report.failed:
    print(report.render())
d.dataset   # {"name": "boj", "title": …, "documents": ["README.md", "methodology.md"], "image": "docs/cover.png"}
d.schemas   # [{"name": "timeseries", "title": "Time series"}]
d.tables    # [{"schema": "timeseries", "name": "series", "sql": …, "depends_on": […], "documents": ["timeseries/series/README.md"], "columns": […]}]
d.files     # [File(path="README.md", sha256="…", bytes=1234, media_type="text/markdown", local="README.md"), …]
d.source    # {"repository": "https://github.com/…", "commit": "…", "path": "", "dirty": False}
d.dependencies  # {"other": {"url": "https://…"}}: SQL が読むほかのデータセット (SQL の中の名前 → URL)。FDL の tables.json の dependencies と同じ形
d.content(d.files[0])  # そのファイルの中身
```

- `source` は Git の作業コピーから取ります。`repository` は `origin` の URL を https に直したもの (認証情報と `.git` を外す)、`commit` は HEAD、`path` はリポジトリのルートから tabledoc.yml のフォルダまでのパス、`dirty` はコミットしていない変更があるかです。Git の外と `Options(with_source=False)` では None です
- 文書はパスで参照します。`files` に、説明と一緒に送るファイル (文書とそれらが指すファイル) を[データセットの中のパス](#データセットの中のパス)・sha256・大きさ・メディアタイプと、ルートからのパス `local` で並べます。`documents` (`schemas[].documents` も) の値は `files` のパスで、ファイル名が `README.md` のものがガイドです。`content` はデータセットに入れる中身を返します。Markdown の文書はリンクを書き換えた本文、以前の形式の Markdown のテーブルのファイルはフロントマターを外した本文です
- `id` だけで書いたライセンスと出典は、それを定義した項目にして返します
- テーブルは `schema`・`name` の順に並べ、キーの順も決まっています。同じファイルからは同じ値を返します
- 構造 (型・NULL・行数・ビューかどうか) は入れません

## テーブル

説明をテーブルで表したものです。データと同じデータベースの、スキーマ `_tabledoc` のテーブルに置きます。テーブルは第三正規形です。どのセルも値を 1 つだけ持ち (一覧・STRUCT・JSON を持たない)、1 つの事実は 1 つのテーブルの 1 行にだけあります。

- 行が何についてのものかは `schema_name`・`table_name`・`column_name` で表します。当たらない段は `''` です。データセットの行は 3 つとも `''`、スキーマの行は `table_name` と `column_name` が `''`、テーブルの行は `column_name` が `''` です
- ほかのテーブルの行を指す列の名前は「指す先のテーブルの単数形_その主キー」にします (`license_id`・`source_id`・`contributor_id`)
- テーブル名は複数形です。キーごとに 1 行を持つ `dataset` だけは単数形です
- データベースの外部キーは使いません。書き手は、各行が指す行のあることを確認してから書きます
- テーブルは今の説明だけを持ちます。過去のバージョンはカタログが持ちます

| テーブル | 主キー | ほかの列 |
| --- | --- | --- |
| `dataset` | `key` | `value`。キーは `name`・`language`・`homepage`・`repository`・`issued` (`YYYY-MM-DD`)・`update_frequency`・`image` (`files` の `path`)・`temporal_start`・`temporal_end` です |
| `schemas` | `schema_name` | |
| `tables` | `schema_name`・`table_name` | `hidden` (説明に `true` と書かない限り `false`)・`temporal_start`・`temporal_end`・`sql`・`source_path` |
| `columns` | `schema_name`・`table_name`・`column_name` | `key_position` (主キーの中での列の位置。0 から数え、主キーに無い列は NULL)・`entity` (値のコード体系の名前。`city` など)・`dimension` (`categorical` か `time`)・`granularity` |
| `metrics` | `schema_name`・`table_name`・`metric_name` | `agg`・`expr`・`description` |
| `descriptions` | `schema_name`・`table_name`・`column_name`・`language` | `title`・`title_reading`・`description` |
| `topics` | `schema_name`・`table_name`・`column_name`・`language`・`topic` | |
| `synonyms` | `schema_name`・`table_name`・`column_name`・`language`・`synonym` | |
| `licenses` | `id` | `url`・`title`・`commercial_use`・`share_alike`・`attribution_required` |
| `table_licenses` | `schema_name`・`table_name`・`license_id` | `position` |
| `sources` | `id` | `title`・`url` |
| `table_sources` | `schema_name`・`table_name`・`source_id` | `position` |
| `contributors` | `id` | `title`・`url`・`position` |
| `contributor_roles` | `contributor_id`・`role` | |
| `table_areas` | `schema_name`・`table_name`・`area` | `position` (`spatial_coverage` の地域) |
| `table_dependencies` | `schema_name`・`table_name`・`depends_on` | (このデータセットのテーブルは `<schema>.<table>`、ほかのデータセットのテーブルは `<dataset>.<schema>.<table>`) |
| `files` | `path` | `sha256`・`bytes`・`media_type` ([データセットの中のファイル](#データセットの中のパス)) |

- `descriptions`・`topics`・`synonyms` は、データセット・スキーマ・テーブル・列のどれかについての行です。`table_licenses`・`table_sources`・`table_areas` は、データセットかテーブルについての行です
- `position` は書いた順番で、0 から数えます
- ファイルで日付や数値で書いた値 (`issued`・`temporal_start`) は文字列で持ちます
- `files` は、文書とそれが指すファイルを sha256 で示します。ファイルそのものは、カタログかその横に置きます (FDL ではデータセットの asset)
- テーブルは、説明した列と主キーの列ごとに `columns` の行を持ちます
- 列がファイルのパスを持つかどうか (`asset`) はこれらのテーブルに書きません。カタログが持ちます (FDL では宣言)

### 各テーブルの作り方

テーブルのうち `tables.sql`・`tables.source_path`・`table_dependencies` の 3 つは、テーブルの意味ではなく、テーブルをどう作ったかを示します。人は書きません。ツールがビルドから埋めます (`tabledoc load` が dbt の manifest から)。読み手はテーブルの系譜として表示します。ビルドは `sql` を前のバージョンと比較して、SQL の変わらないテーブルの作り直しを省けます。

### プロファイル

データから数えた値を持つテーブルが 3 つあります。読み手がその値で検索するためのもので、置くかどうかは任意です。人は書きません。プログラムがデータ (DuckLake や Iceberg の列の統計、または SQL の集計) から数えて書き、データが変わったらマージせずに書き直します。[FDL のプロファイル](https://fdl.queria.io/ja/spec/versions#profiles) と同じ値を同じ名前で持ちます。

| テーブル | 主キー | ほかの列 |
| --- | --- | --- |
| `table_profiles` | `schema_name`・`table_name` | `rows` |
| `column_profiles` | `schema_name`・`table_name`・`column_name` | `null_count`・`distinct_count`・`min`・`max` (文字列) |
| `column_values` | `schema_name`・`table_name`・`column_name`・`value` | `count`: その値を持つ行の数。異なる値が 2,000 個以下の列はすべての値、それより多い列は多い順に 10 個 |

FDL では、各バージョンのプロファイルを FDL 自身のファイルとして持ち、これらのテーブルには書きません。複数のデータセットをまたぐ検索は読み手が行います。読み手は各データセットのテーブルを集めて、自分の索引を作ります。

## DuckLake のカタログに書く

`tabledoc load` は `validate` と同じ検査をしてから、説明を [DuckLake](https://ducklake.select) のカタログの[テーブル](#テーブル)に書きます。スキーマは `_tabledoc` で、`--schema` で変えられます。fdl では、カタログは `fdl clone` が作る作業用メタデータで、`fdl commit` でバージョンにします。

```bash
tabledoc load --ducklake work.sqlite --out build/assets
fdl commit work.sqlite -m "..." --assets build/assets
```

- `--ducklake`: カタログ (既定は `FDL_WORKING`)。`--data-path`: 新しいデータファイルを置く場所 (既定は `FDL_DATA_PATH`、無ければ fdl の作業用メタデータについて `fdl status --json` が返す `data_path`)。HTTP のデータファイルは DuckDB の secret で読みます。カタログが fdl の作業用メタデータで `FDL_TOKEN` があるときは、`fdl status --json` が返す `remote` にそのトークンを送るので、非公開データセットのファイルも読めます
- `--schema`: 書くスキーマ (既定は `_tabledoc`)
- `--out`: `fdl commit --assets` に渡すフォルダも書きます。`files` テーブルの各ファイルを `files/<path>` に置きます。`--assets <フォルダ>` を付けると、その下のファイル (ビルドが作った asset の列のファイル) を `data/` にリンクします。フォルダは空か前の `load` が書いたもので、fdl だけが書く `.fdl/` の外でなければなりません
- `--hide-undescribed`: 説明の無いテーブルとビューにも `tables` の行を作り、`hidden` を true にします。dbt が作ったテーブルで、SQL のほかに説明がどこにも書かれていないものも `hidden` を true にします。書き込むスキーマと、`dataset`・`schemas`・`tables`・`columns`・`files` のテーブルをすべて持つスキーマ (以前の load が書いたスキーマなど) のテーブルには行を作りません
- 説明や主キーにあってカタログに無いテーブルと列、`varchar` でない `asset` の列はエラーです。名前は DuckDB と同じく大文字と小文字を区別せずに照合し、カタログの表記で書きます
- 列に入らない値 (`YYYY-MM-DD` 以外の `issued` など) と、指す先の行が無い行はエラーです
- エラー (`--strict` では警告も) があると何も書きません
- 行は主キーごとに追加・更新・削除するので、`load` は値の違うセルだけを変えます。dbt のビルドが無いとき (説明に `sql` が無いとき) は、各テーブルの `sql`・`source_path`・`table_dependencies` をカタログから引き継ぎます
- `source_path` はそのテーブルを定義しているファイルの、`repository` のルートからのパス (dbt の `original_file_path` に、Git の作業コピーの中での `tabledoc.yml` のフォルダを前に付けたもの)、`sql` はそのテーブルを作った SQL です。判定できないときはどちらも NULL です。テーブルかビューかは書きません (カタログが持っています)
- ビューの行には `sql` と `table_dependencies` を書きません。ビューの SQL はメタデータが持ちます
- `repository` は `tabledoc.yml` の `repository`、無ければ Git の `origin` を https にしたものです
- 以前の tabledoc が書いた、この規約のものでないテーブル (`texts`) と、この規約のテーブルにある規約のものでない列は削除します。スキーマのほかのテーブルはそのまま残します。プロファイルのテーブルは書かず、そのまま残します
- asset の列はこれらのテーブルに書きません。カタログが `fdl clone` の作った作業用メタデータのとき (横に `<catalog>.fdl` フォルダがあるとき)、`load` は `fdl declare` で FDL に宣言します (fdl-cli 0.35 以降の `fdl` が `PATH` にあることが必要です)。宣言するのは、各テーブルの `primary_key` と、列に `asset` があるテーブルの asset の列 (ビューにはどちらも宣言しません)、`hidden` が true のテーブルとビューにプロファイルを作らないことと、説明したほかのテーブルにプロファイルを作ること、SQL が読むほかのデータセット (dbt の `profiles.yml` から) の依存先、それにこれらのテーブルの主キーと asset の列 `files.sha256` とプロファイルを作らないことです。`fdl declare list` と違うものだけを実行し、説明に無いものは FDL の宣言のまま残します
- コメント (`COMMENT ON`) は書きません

## カタログからファイルを書く

`tabledoc dump` は、カタログが持つ説明のファイルを書きます。`tabledoc.yml`、説明のあるテーブルごとのテーブルのファイル、`files` テーブルの各ファイル (そのパスに) です。書いたファイルを `tabledoc load` で読むと、同じテーブルになります。

```bash
tabledoc dump --ducklake work.sqlite --out description/
```

- `--ducklake`: カタログ (既定は `FDL_WORKING`)。`--schema`: 説明のあるスキーマ (既定は `_tabledoc`)。`--out`: 書くフォルダ (既定は今のフォルダ)。`.fdl/` の外でなければなりません
- `--files`: `files` テーブルのファイルの置き場所。`<files>/<sha256>` で読みます。フォルダか http(s) の URL です。既定は、fdl の作業用メタデータについて `fdl status --json` が返す `remote` の `assets/` です。各ファイルは sha256 で照合します
- `--name`: `tabledoc.yml` の `name`。既定は `dataset` テーブルの `name`、無ければリポジトリの URL の最後の部分です
- フォルダに同じファイルがあると、`--force` を付けない限り何も書きません。カタログのパスがフォルダの外を指すときはエラーです
- テーブルのファイルは `<schema>/<table>.tabledoc.yml` に書きます。ファイルはデータセットの中のパスのまま書き、フォルダの Markdown (`README.md` を先頭に) を、そのフォルダが説明する対象の `documents` に並べます。ルートの `README.md` は並べなくてもデータセットの説明です
- 文字列は、1 つの言語だけでそれがデータセットの `language` なら文字列だけで、それ以外は対応で書きます
- ライセンスと出典は、最初に使う場所 (データセット、次にテーブルを名前の順) に全部書き、その後は `id` だけを書きます。`id` しか持たないライセンスは `id` だけを書きます
- テーブルに無いものは書きません。asset の列、`annotations` と、dbt の `profiles.yml` から取る SQL が読むほかのデータセットです。`--hide-undescribed` だけが書いたテーブルにはテーブルのファイルを作りません。`sql` と `depends_on` は `source_path` の無いテーブル (dbt で作らないテーブル) にだけ書きます

## AI のために Markdown を書き出す

`tabledoc export --markdown <フォルダ>` は、`validate` と同じく説明を検査してから、Markdown として書き出します。データセットに 1 つ、スキーマごとに 1 つ、テーブルごとに 1 つのファイルを書きます。AI アシスタントや人はこのフォルダをそのまま読めます。データのドキュメントと一緒に公開することもできます。

```bash
tabledoc export --markdown ai-docs/
```

| ファイル | 内容 |
| --- | --- |
| `README.md` | データセットの名前、説明、ライセンス、出典など `tabledoc.yml` のキー。スキーマとテーブルの一覧 (それぞれへのリンクと、説明の最初の段落)。文書の一覧。最後にデータセットの概要 (`README.md`) |
| `<schema>/README.md` | スキーマの名前と説明、テーブルと文書の一覧。最後にスキーマのガイド |
| `<schema>/<table>/README.md` | テーブルの名前、説明、主キー、ライセンス、出典、`materialized`。列 (名前、説明、semantic、`asset`) とメトリクスの表。そのテーブルが読むテーブルと、そのテーブルを読むテーブル (データセットの中のテーブルはリンク)。SQL。文書の一覧。最後にテーブルのガイド |

- ファイルは [データセットの中のパス](#データセットの中のパス) に書きます。`files` のほかのファイル (文書、画像) もそれぞれのパスに書くので、ガイドの中のリンクはそのまま使えます
- ガイドは区切り線 (`---`) の後に、書かれたとおりに置きます。見出しのレベルは変えません
- 複数の言語で書いた値は、データセットの `language` のもの (無ければ und、それも無ければタグの順で最初のもの) を書きます
- ほかの読み手のキー (`annotations:`) は書きません
- 型・NULL の可否・行数は説明に含まれないので、書きません
- フォルダに同じパスのファイルがあると、`--force` を付けない限り何も書きません。前の書き出しにあって今回書かないファイルは、フォルダに残ります
- フォルダには `.tabledoc-export` というファイルも書きます。tabledoc はこのファイルがあるフォルダの中のファイルを読まないので、書き出すフォルダをルートの中に置けます
- エラーがあると (`--strict` では警告も) 何も書きません

## 以前の形式

すべてのデータセットを一度に書き換えずに済むように、tabledoc は置き換える前の形式も読みます。新しく書くのは tabledoc の形式だけです。

- `tabledoc.yml` が無く `queria.yml` (`https://queria.io/schemas/dataset/v1.json`) があれば、それを tabledoc.yml として読みます。`title_kana` は `title_reading`、`cover` はファイルのパス (拡張子のあるもの) のときだけ `image`、`ai_context` の `synonyms` は `synonyms` として読みます。`themes` と `ai_context` のほかの値は読みません。`catalogs` は `depends_on` に使い、`dependencies` として返します
- 以前の形式のファイルの出典と作成者の `path` は `url` として読みます。`id` の無いものは `path` (無ければ `title`) を `id` にします
- フロントマターに `$schema: https://queria.io/schemas/table/v1.json` を持つ Markdown は、フロントマターをテーブルのファイル、本文をガイドとして読みます。`table:` で対応を決め、`fields` は `columns`、`published: false` は `hidden: true` として読みます。`ai_context` と `themes` は `queria.yml` と同じく扱います。ガイドはその Markdown のパスで、送る本文はフロントマターを外したものです
- 列の `semantic: {role, name, agg}` は次のように読み替えます。`role: entity` → `entity: <name>`。`role: dimension` → `dimension: categorical`。`role: measure` → テーブルの metrics に `{name: <列名>, agg, expr: <列名>}` (`agg` が無ければ警告)
- `docs` (`schemas[].docs` も) は `documents`、スキーマの `guide` はそのスキーマの `documents` の 1 つとして読みます
- 同じフォルダに `tabledoc.yml` と `queria.yml` があるとエラーになります

## $schema とバージョン

- JSON Schema は tabledoc に同梱し、`https://tabledoc.queria.io/schemas/<種類>/v<n>.json` で配ります。種類は `dataset` と `table` です
- キーを追加するだけなら同じバージョンのままです。`v1` を固定するまでは、キーの名前を変えたり消したりすることがあります。そのとき tabledoc はこのページのキーだけを読みます。固定した後は、キーの意味を変える・消すときに `v2` にし、tabledoc はしばらく両方を読みます
- 知らない `$schema` のファイルは断り、tabledoc を上げるよう伝えます
