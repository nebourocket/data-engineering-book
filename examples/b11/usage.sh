#!/bin/bash
# 第 11 章: リポジトリの直下で動かす（work/ に出力が作られる）

# 月ごとの Parquet を作り、4 通りのクエリで開いたファイル数と読んだバイト数を測る
python examples/b11/partition_demo.py

# 1 つのクエリの EXPLAIN ANALYZE を見る
python examples/b11/run_query.py explain_month

# 部分集計と合算（平均は、平均の平均にならない）
python examples/b11/run_query.py monthly_partial
python examples/b11/run_query.py combine_partials

# 並べ方で行グループの読み飛ばしが変わる
python examples/b11/clustering_demo.py
