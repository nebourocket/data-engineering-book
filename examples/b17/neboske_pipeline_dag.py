"""第17章のパイプライン (pipeline.py) を、Airflow で毎朝動かす DAG。取り込み → dbt → 品質チェックの 3 タスクです。"""
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow.sdk import dag, task
from airflow.timetables.interval import CronDataIntervalTimetable

REPO = Path(__file__).resolve().parents[2]
WORKDIR = Path(os.environ.get("NEBOSKE_WORK", REPO / "work")) / "b17-airflow"
PYTHON = os.environ.get("PIPELINE_PYTHON", sys.executable)  # dbt と DuckDB が入った Python (Airflow と別でよい)
TZ = "Asia/Tokyo"  # 日付の区切りに使うタイムゾーン (第12章と同じ)


def day_of(data_interval_start: datetime) -> str:
    """処理する日 (区間の始まりの日付) を '2026-07-01' の形にします (第12章と同じ)。"""
    return data_interval_start.astimezone(ZoneInfo(TZ)).strftime("%Y-%m-%d")


def notify_failure(context) -> None:
    """失敗を通知する場所です。ここではログに書くだけです (実際はチャットやメールに送ります)。"""
    ti = context["task_instance"]
    logging.getLogger(__name__).error("失敗: %s / %s", ti.dag_id, ti.task_id)


def run_step(step: str, data_interval_start: datetime) -> None:
    """pipeline.py の 1 工程を、別のプロセスとして呼びます。失敗 (終了コードが 0 以外) なら例外になり、タスクは失敗します。"""
    subprocess.run(
        [PYTHON, str(REPO / "examples/b17/pipeline.py"), "--step", step,
         "--dt", day_of(data_interval_start), "--workdir", str(WORKDIR)],
        check=True, cwd=REPO)


@task
def ingest_raw(data_interval_start=None) -> None:
    run_step("ingest", data_interval_start)


@task
def dbt_build(data_interval_start=None) -> None:
    run_step("dbt", data_interval_start)


@task
def quality_checks(data_interval_start=None) -> None:
    run_step("checks", data_interval_start)


@dag(
    dag_id="neboske_pipeline",
    schedule=CronDataIntervalTimetable("0 6 * * *", timezone=TZ),
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=30),
        "on_failure_callback": notify_failure,
    },
    tags=["book"],
)
def neboske_pipeline():
    ingest_raw() >> dbt_build() >> quality_checks()


neboske_pipeline()
