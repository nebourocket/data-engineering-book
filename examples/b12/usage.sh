#!/bin/bash
# 第 12 章: リポジトリの直下で動かす（work/ に出力が作られる）

# 入力の CSV を、日付ごとのフォルダに作る
python examples/b12/make_source.py

# 1 日分を作る。同じ日をもう一度流しても、中身は変わらない
python examples/b12/daily_job.py 2026-03-05
cat work/out/daily_sales/date=2026-03-05.csv

# バックフィル: 期間の各日を作り直す
python examples/b12/daily_job.py 2026-03-01 2026-03-07
ls work/out/daily_sales

# 悪い例: 追記するジョブは、同じ日を 2 回流すと合計が 2 倍になる
python examples/b12/naive_job.py 2026-03-05
python examples/b12/naive_job.py 2026-03-05

# 依存の順に動かす小さな実行器
python examples/b12/mini_runner.py

# テスト（再実行とバックフィルの確認）
pytest -q examples/b12
