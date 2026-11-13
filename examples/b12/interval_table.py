"""第 12 章: 日次 DAG の「データの区間」と「処理する日」の対応表を、コードで計算して CSV に書きます。

使い方: python examples/b12/interval_table.py
区間は日本時間の 0 時から翌日 0 時まで。定期の実行は区間が終わった直後に始まり、
手動の実行（airflow dags test など）は「指定した論理日付の直前の、終わった区間」を処理します。
"""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parents[2] / "data" / "tables" / "b12-interval-timeline.csv"
JST = ZoneInfo("Asia/Tokyo")
HEADER = ["どの実行か", "実行が始まる時刻（日本時間）", "論理日付（UTC）", "data_interval_start（日本時間）", "data_interval_end（日本時間）", "処理する日"]


def fmt(t: datetime) -> str:
    return t.astimezone(JST).strftime("%Y-%m-%d %H:%M")


def scheduled(day: str) -> list[str]:
    """定期の実行: 区間は day の 0 時〜翌日 0 時。"""
    start = datetime.fromisoformat(day).replace(tzinfo=JST)
    end = start + timedelta(days=1)
    return [f"定期（{day} の分）", f"{fmt(end)} 以降（区間が終わった直後）", "（区間の始まりと同じ）", fmt(start), fmt(end), day]


def manual(logical_utc: str) -> list[str]:
    """手動の実行: 論理日付を日本時間に直し、その時刻より前に終わった最後の区間を使う。"""
    logical = datetime.fromisoformat(logical_utc).replace(tzinfo=timezone.utc)
    end = logical.astimezone(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    return [f"手動（dags test {logical.date()}）", "コマンドを実行した時刻", logical.strftime("%Y-%m-%d %H:%M"), fmt(start), fmt(end),
            start.strftime("%Y-%m-%d")]


def rows() -> list[list[str]]:
    return [scheduled("2026-03-03"), scheduled("2026-03-04"), manual("2026-03-05")]


if __name__ == "__main__":
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(rows())
    print(f"{OUT.name} を書きました")
