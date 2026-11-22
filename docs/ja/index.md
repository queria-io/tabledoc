---
title: tabledoc
sidebar:
  label: はじめに
  order: 1
description: YAML と Markdown (または dbt のプロジェクトの yml) で書いたデータセットの説明を検査し、ほかのプログラムのために読みます。
---

tabledoc は、人が YAML と Markdown (または dbt のプロジェクトの yml) で書くデータセットの説明を検査し、ほかのプログラムのために読むツールです。

- テーブルごとに YAML を 1 つ書き、隣に Markdown のガイドを置きます。キーは dbt の `models:` の項目と同じです
- semantic (結合キー・ディメンション・メトリクス) は dbt のセマンティックレイヤーの書き方にそろえています
- dbt のプロジェクトでは、説明・SQL・依存関係を `target/manifest.json` から取ります
- Python からは `tabledoc.read` で、検査した説明を読めます。ガイドとそこから参照するファイルはパスと sha256 で並べます
- `tabledoc load` は説明を DuckLake のカタログに、1 つのスキーマ (既定は `_queria`) の普通のテーブルとして書きます。説明はデータと一緒に配布され、[FDL](https://fdl.queria.io) でデータと一緒にバージョン管理されます。`tabledoc dump` はそこからファイルを書き戻します

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
tabledoc load --ducklake work.sqlite   # 検査して、カタログの _queria スキーマに書く
tabledoc dump --ducklake work.sqlite --out description/   # カタログからファイルを書き戻す
```

dbt のプロジェクトでは先に `dbt compile` を実行し、`dbt_project.yml` の隣に `tabledoc.yml` を書きます。

## 仕様

ファイル・検査・`tabledoc.read` が返す値は[仕様](/ja/spec)で定めています。JSON Schema は `https://queria-io.github.io/tabledoc/schemas/` で配っています。
