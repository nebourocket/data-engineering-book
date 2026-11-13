#!/usr/bin/env bash
# サンプルの注文 CSV を作り、ETL を動かします (リポジトリの直下から実行します)。
set -euo pipefail
export PYTHONPATH=.
python -m examples.b04.make_sample /tmp/orders.csv

cd examples/b04
export ETL_INPUT=/tmp/orders.csv ETL_OUTPUT_DIR=/tmp/out
python -m neboske_etl
LOG_LEVEL=DEBUG python -m neboske_etl
ETL_MAX_REJECT_RATIO=0.0001 python -m neboske_etl || echo "終了コード: $?"
