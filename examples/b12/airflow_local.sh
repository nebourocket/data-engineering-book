#!/bin/bash
# 手元に Airflow を入れて DAG を 1 回動かす例（Linux / WSL / macOS。Windows 直下では動きません）。
# 本書のテストでは実行しません。CI では、DAG ファイルが読み込めることだけを確かめています。
pip install "apache-airflow==2.10.5" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.12.txt"

export AIRFLOW_HOME="$PWD/work/airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/examples/b12"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export NEBOSKE_WORK="$PWD/work"

python examples/b12/make_source.py
airflow dags test neboske_daily_sales 2026-03-05
