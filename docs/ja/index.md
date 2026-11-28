---
title: tabledoc
sidebar:
  label: はじめに
  order: 1
description: dbt の manifest と人や AI が書いた説明から、データセットのテーブルを人と AI が読める形にします。
---

tabledoc は、データセットのテーブルを人と AI が読める形にするツールです。dbt がテーブルについて持っている情報 (`target/manifest.json` の説明・SQL・依存関係) に、人や AI が YAML と Markdown で書いた説明 (名前、列の説明、識別子、ガイド) を重ねて検査し、Markdown のファイルか DuckLake のカタログのテーブルとして書き出します。

- テーブルごとに YAML を 1 つ書き、隣に Markdown のガイドを置きます。キーは dbt の `models:` の項目と同じです
- semantic (識別子・ディメンション・メトリクス) は dbt のセマンティックレイヤーの書き方に合わせています
- dbt のプロジェクトでは、説明・SQL・依存関係を `target/manifest.json` から取ります
- Python からは `tabledoc.read` で、検査した説明を読めます。ガイドとそこから参照するファイルはパスと sha256 で並べます
- `tabledoc export --markdown <フォルダ>` は、テーブルごとに Markdown のファイルを 1 つ (列、semantic、主キー、依存関係、SQL、ガイド) と、それらを一覧にするデータセットのファイルを書き出します。AI アシスタントや人がそのまま読めます
- 同じ説明をテーブルでも表せます。スキーマ `_tabledoc` の第三正規形のテーブルで、SQL のデータベースならデータの隣に置けます。`tabledoc load` はそれを DuckLake のカタログに書き、説明はデータと一緒にバージョン管理されます ([FDL](https://fdl.queria.io) など)。`tabledoc dump` はそこからファイルを書き戻します

## インストール

```bash
uv tool install tabledoc   # または pip install tabledoc
```

## 使い方

```
tabledoc.yml                  データセット
README.md                     データセットの概要
sales/orders.tabledoc.yml     テーブル sales.orders
sales/orders.md               そのガイド
```

```yaml
# tabledoc.yml
$schema: https://tabledoc.queria.io/schemas/dataset/v1.json
name: shop
title: 店舗の売上
language: ja
licenses: [CC-BY-4.0]
```

```yaml
# sales/orders.tabledoc.yml
$schema: https://tabledoc.queria.io/schemas/table/v1.json
title: 注文
description: 1 行が 1 件の注文です。
primary_key: [order_id]
columns:
  - name: city_code
    entity: city
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
tabledoc profile --ducklake lake.sqlite   # データを数えてプロファイルのテーブルに書く (fdl を使わないとき)
tabledoc export --markdown ai-docs/   # テーブルごとの Markdown を書き出す
```

dbt のプロジェクトでは先に `dbt compile` を実行し、`dbt_project.yml` の隣に `tabledoc.yml` を書きます。

## 仕様

ファイル・検査・`tabledoc.read` が返す値は[仕様](/ja/spec)で定めています。JSON Schema は `https://tabledoc.queria.io/schemas/` で配っています。
