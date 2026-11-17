<p align="center"><img src="assets/icon.svg" width="96" alt=""></p>

# tabledoc

[English](README.md)

tabledoc は、人が YAML と Markdown (または dbt のプロジェクトの yml) で書くデータセットの説明を検査し、機械が読む 1 つの JSON (`tabledoc.json`) を作るツールです。

- テーブルごとに YAML を 1 つ書き、隣に Markdown のガイドを置きます。キーは dbt の `models:` の項目と同じです
- semantic (結合キー・ディメンション・メトリクス) は dbt のセマンティックレイヤーの書き方にそろえています
- dbt のプロジェクトでは、説明・SQL・依存関係を `target/manifest.json` から取ります
- `tabledoc.json` はガイドとそこから参照するファイルをパスと sha256 で並べます。`tabledoc push` は受け手に無いファイルを送ります

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
tabledoc build               # 検査して target/tabledoc.json を書く
tabledoc push https://example.com/metadata   # 送る。TABLEDOC_TOKEN を Bearer トークンに使う
```

dbt のプロジェクトでは先に `dbt compile` を実行し、`dbt_project.yml` の隣に `tabledoc.yml` を書きます。

## 仕様

[docs/ja/spec.md](docs/ja/spec.md) ([English](docs/spec.md))。JSON Schema は [src/tabledoc/schemas](src/tabledoc/schemas) にあり、`https://queria-io.github.io/tabledoc/schemas/` で配っています。

## ライセンス

MIT
