#!/bin/bash
# 手元に Airflow 3 を入れて DAG を 1 回動かす例（Linux / WSL / macOS。Windows 直下では動きません）。
pip install "apache-airflow==3.4.0" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.4.0/constraints-3.12.txt"

export AIRFLOW_HOME="$PWD/work/airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/examples/b12"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export NEBOSKE_WORK="$PWD/work"

python examples/b12/make_source.py
airflow db migrate
airflow dags test neboske_daily_sales 2026-03-05

# 過去の期間の作り直し（バックフィル）。3 系のコマンド。スケジューラが動いているときに使う（本書では実行していません）
airflow backfill create --dag-id neboske_daily_sales --from-date 2026-03-01 --to-date 2026-03-07

# 過去の期間の作り直し（バックフィル）。3 系のコマンド。スケジューラが動いているときに使う（本書では実行していません）
airflow backfill create --dag-id neboske_daily_sales --from-date 2026-03-01 --to-date 2026-03-07
