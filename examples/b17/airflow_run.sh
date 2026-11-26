#!/bin/bash
# 第17章のパイプラインを Airflow の DAG として 1 回動かす例 (リポジトリの直下で。Linux / WSL / macOS)。
# Airflow は第12章の airflow_local.sh と同じ手順で、別の仮想環境 (.venv) に入れておきます。
# dbt と DuckDB が入った Python は PIPELINE_PYTHON で渡します (開発用イメージの python など)。
source .venv/bin/activate
export AIRFLOW_HOME="$PWD/work/airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/examples/b17"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export PIPELINE_PYTHON="${PIPELINE_PYTHON:-python3}"

airflow db migrate
airflow dags test neboske_pipeline 2026-07-02
# 同じ日 (論理日付 7/2 は、前日 7/1 の分を処理します) をもう一度流しても、結果は変わらない (冪等)
airflow dags test neboske_pipeline 2026-07-02
