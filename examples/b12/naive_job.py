"""第 12 章 練習問題 4: 冪等でない日次ジョブ（悪い例）。結果を 1 つのファイルに追記します。

使い方: python examples/b12/naive_job.py 2026-03-05   （同じ日を 2 回流すと、売上の合計が 2 倍になります）
"""
import csv
import sys
from pathlib import Path

import duckdb


def process_append(day: str, source_root: Path, out_file: Path) -> None:
    """day の売上をカテゴリ別に集計して、out_file の末尾に足します（置き換えではなく追記）。"""
    rows = duckdb.connect().execute(
        "SELECT ?, category, sum(quantity * unit_price) FROM read_csv(?, types = {'quantity': 'INTEGER', 'unit_price': 'INTEGER'}) "
        "WHERE lower(COALESCE(status, '')) <> 'cancelled' GROUP BY category",
        [day, str(source_root / f"date={day}" / "sales.csv")]).fetchall()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def total(out_file: Path) -> int:
    """out_file の売上の合計を返します。"""
    with out_file.open(encoding="utf-8", newline="") as f:
        return sum(int(row[2]) for row in csv.reader(f))


if __name__ == "__main__":
    out = Path("work/out/naive_sales.csv")
    process_append(sys.argv[1], Path("work/source"), out)
    print(f"売上の合計: {total(out):,}")
