"""ねぼすけ商店の日次売上を作る DAG（第 12 章）。処理の本体は daily_job.py にあります。"""
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow.sdk import dag, task
from airflow.timetables.interval import CronDataIntervalTimetable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_job  # noqa: E402

WORK = Path(os.environ.get("NEBOSKE_WORK", "/tmp/neboske"))
SOURCE = WORK / "source"
OUT = WORK / "out"
TZ = "Asia/Tokyo"  # 日付の区切りに使うタイムゾーン（元データの日付は日本時間）


def day_of(data_interval_start: datetime) -> str:
    """処理する日（区間の始まりの日付）を '2026-03-05' の形にする。

    data_interval_start は UTC で渡ってくるので、スケジュールと同じタイムゾーンに直してから日付にする。
    """
    return data_interval_start.astimezone(ZoneInfo(TZ)).strftime("%Y-%m-%d")


def notify_failure(context) -> None:
    """失敗を通知する場所。ここではログに書くだけです（実際はチャットやメールに送ります）。"""
    ti = context["task_instance"]
    logging.getLogger(__name__).error("失敗: %s / %s", ti.dag_id, ti.task_id)


@task.sensor(poke_interval=300, timeout=6 * 60 * 60, mode="reschedule")
def wait_for_source(data_interval_start=None) -> bool:
    """その日の元データの完了の印（_SUCCESS）が届くまで待つ。待っている間はワーカーを空けておく（reschedule）。"""
    return daily_job.source_ready(day_of(data_interval_start), SOURCE)


@task
def build(data_interval_start=None) -> dict:
    """その日の分だけを作り直す。同じ日を再実行しても、結果は変わらない。"""
    day = day_of(data_interval_start)
    return {"day": day, "rows": daily_job.process(day, SOURCE, OUT)}


@task
def report(result: dict) -> None:
    """前のタスクの結果は、小さな dict（日付と行数）だけを XCom で受け取る。"""
    logging.getLogger(__name__).info("%s: %d 行を書きました", result["day"], result["rows"])


@dag(
    dag_id="neboske_daily_sales",
    schedule=CronDataIntervalTimetable("0 0 * * *", timezone=TZ),
    start_date=datetime(2026, 1, 1),
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
def neboske_daily_sales():
    ready = wait_for_source()
    result = build()
    ready >> result
    report(result)


neboske_daily_sales()
