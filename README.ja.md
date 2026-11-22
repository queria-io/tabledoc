<p align="center"><img src="public/icon.svg" width="96" alt=""></p>

# tabledoc

[English](README.md)

tabledoc は、データセットのテーブルを人と AI が読める形にするツールです。dbt がテーブルについて持っている情報 (`target/manifest.json` の説明・SQL・依存関係) に、人や AI が YAML と Markdown で書いた説明 (名前、列の説明、結合キー、ガイド) を重ねて検査し、Markdown のファイルか DuckLake のカタログのテーブルとして書き出します。

- テーブルごとに YAML を 1 つ書き、隣に Markdown のガイドを置きます。キーは dbt の `models:` の項目と同じです
- semantic (結合キー・ディメンション・メトリクス) は dbt のセマンティックレイヤーの書き方にそろえています
- dbt のプロジェクトでは、説明・SQL・依存関係を `target/manifest.json` から取ります
- Python からは `tabledoc.read` で、検査した説明を読めます。ガイドとそこから参照するファイルはパスと sha256 で並べます
- `tabledoc export --markdown <フォルダ>` は、テーブルごとに Markdown のファイルを 1 つ (列、semantic、主キー、依存関係、SQL、ガイド) と、それらを一覧にするデータセットのファイルを書き出します。AI アシスタントや人がそのまま読めます
- `tabledoc load` は説明を DuckLake のカタログに、1 つのスキーマ (既定は `_tabledoc`) の普通のテーブルとして書きます。説明はデータと一緒に配布され、[FDL](https://fdl.queria.io) でデータと一緒にバージョン管理されます。`tabledoc dump` はそこからファイルを書き戻します

## インストール

```bash
uv tool install tabledoc   # または pip install tabledoc
```

## 使い方

```
tabledoc.yml              データセット
README.md                 データセットの概要
sales/orders.yml          テーブル sales.orders
sales/orders.md           そのガイド
```

```yaml
# tabledoc.yml
$schema: https://queria-io.github.io/tabledoc/schemas/dataset/v1.json
name: shop
title: 店舗の売上
language: ja
licenses: [CC-BY-4.0]
```

```yaml
# sales/orders.yml
$schema: https://queria-io.github.io/tabledoc/schemas/table/v1.json
title: 注文
description: 1 行が 1 件の注文です。
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
tabledoc validate            # 検査する
tabledoc load --ducklake work.sqlite   # 検査して、カタログの _tabledoc スキーマに書く
tabledoc dump --ducklake work.sqlite --out description/   # カタログからファイルを書き戻す
tabledoc export --markdown ai-docs/   # テーブルごとの Markdown を書き出す
```

dbt のプロジェクトでは先に `dbt compile` を実行し、`dbt_project.yml` の隣に `tabledoc.yml` を書きます。

## 仕様

ドキュメントと仕様は [tabledoc.queria.io/ja](https://tabledoc.queria.io/ja) にあります (元のファイルは [docs/ja/spec.md](docs/ja/spec.md))。JSON Schema は [src/tabledoc/schemas](src/tabledoc/schemas) にあり、`https://queria-io.github.io/tabledoc/schemas/` で配っています。

## ライセンス

MIT
