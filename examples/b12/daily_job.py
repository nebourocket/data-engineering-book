"""第 12 章: 日付を引数に取り、その日の分だけを作り直す日次ジョブ。

使い方: python examples/b12/daily_job.py 2026-03-05            （1 日分）
        python examples/b12/daily_job.py 2026-03-01 2026-03-07  （期間の各日。バックフィル）
work/source/sales.csv（make_source.py が作ります）を読み、work/out/daily_sales/date=2026-03-05.csv を書きます。
同じ日を何度実行しても、結果のファイルは同じ中身になります（冪等）。
"""
import argparse
import csv
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

COLUMNS = ["date", "category", "orders", "revenue"]


def check_day(day: str) -> str:
    """'2026-03-05' の形だけを受け付けます（'2026-3-5' や空文字は ValueError）。"""
    if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
        raise ValueError(f"日付は YYYY-MM-DD の形で渡してください: {day!r}")
    return day


def days_between(start: str, end: str) -> list[str]:
    """start から end まで（両端を含む）の日付を、昇順の文字列で返します。"""
    first = datetime.strptime(check_day(start), "%Y-%m-%d")
    last = datetime.strptime(check_day(end), "%Y-%m-%d")
    if last < first:
        raise ValueError(f"終わりの日が始まりの日より前です: {start} 〜 {end}")
    return [(first + timedelta(days=n)).date().isoformat() for n in range((last - first).days + 1)]


def source_has_day(day: str, source: Path) -> bool:
    """元の CSV があり、その日の明細が 1 行以上あれば True（データが届いた目印）。"""
    if not source.exists():
        return False
    count = duckdb.connect().execute(
        "SELECT count(*) FROM read_csv(?) WHERE CAST(ordered_at AS DATE) = CAST(? AS DATE)",
        [str(source), check_day(day)]).fetchone()[0]
    return count > 0


def process(day: str, source: Path, out_dir: Path) -> int:
    """day の売上をカテゴリ別に集計し、その日のファイルを丸ごと置き換えます。書いた行数を返します。

    追記はしません。書き出しは一時ファイルに行い、最後に os.replace で入れ替えるので、
    途中で失敗しても前回のファイルは壊れず、書きかけが公開されることもありません。
    """
    day = check_day(day)
    rows = duckdb.connect().execute(
        """
        SELECT CAST(? AS DATE) AS date, category, count(DISTINCT order_id) AS orders,
               sum(quantity * unit_price) AS revenue
        FROM read_csv(?)
        WHERE CAST(ordered_at AS DATE) = CAST(? AS DATE) AND lower(status) <> 'cancelled'
        GROUP BY category
        ORDER BY category
        """, [day, str(source), day]).fetchall()

    target = out_dir / "daily_sales" / f"date={day}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{day}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
        os.chmod(tmp, 0o644)  # mkstemp は本人しか読めない 0600 で作るので、読む側のために 0644 にする
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return len(rows)


def backfill(start: str, end: str, source: Path, out_dir: Path) -> dict[str, int]:
    """start から end までの各日を process で作り直します。{日付: 行数} を返します。"""
    return {day: process(day, source, out_dir) for day in days_between(start, end)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="日次ジョブ（日付を引数に取る）")
    parser.add_argument("start", help="処理する日（YYYY-MM-DD）。期間のときは始まりの日")
    parser.add_argument("end", nargs="?", help="期間の終わりの日（含む）")
    args = parser.parse_args()
    results = backfill(args.start, args.end or args.start, Path("work/source/sales.csv"), Path("work/out"))
    for day, n in results.items():
        print(f"{day}: {n} 行")
