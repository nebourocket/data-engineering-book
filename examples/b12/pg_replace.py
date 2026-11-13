"""第 12 章: 結果を PostgreSQL に入れる日次ジョブの、冪等な書き方（1 つのトランザクションで DELETE して INSERT）。

使い方（PostgreSQL に PG_DSN でつなぎます。README の「サービスを使う章」を参照）:
    python examples/b12/pg_replace.py 2026-03-05
先に daily_job.py で work/out/daily_sales/date=2026-03-05.csv を作っておきます。
"""
import csv
import os
import sys
from pathlib import Path

import psycopg

CREATE_TABLE = """
CREATE SCHEMA IF NOT EXISTS b12;
CREATE TABLE IF NOT EXISTS b12.daily_sales (
    date date NOT NULL, category text NOT NULL, orders int NOT NULL, revenue bigint NOT NULL,
    PRIMARY KEY (date, category))
"""


def replace_day(con: psycopg.Connection, day: str, csv_path: Path) -> int:
    """その日の行を消して入れ直します。DELETE と INSERT は 1 つのトランザクションなので、
    途中で失敗すれば両方が取り消され、前回の行がそのまま残ります。入れた行数を返します。"""
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = [(r["date"], r["category"], int(r["orders"]), int(r["revenue"])) for r in csv.DictReader(f)]
    with con.transaction():
        con.execute("DELETE FROM b12.daily_sales WHERE date = %s", [day])
        with con.cursor() as cur:
            cur.executemany("INSERT INTO b12.daily_sales (date, category, orders, revenue) VALUES (%s, %s, %s, %s)",
                            rows)
    return len(rows)


if __name__ == "__main__":
    day = sys.argv[1]
    if "PG_DSN" not in os.environ:
        sys.exit("環境変数 PG_DSN がありません。例: export PG_DSN=postgresql://deb:deb@localhost:5432/deb（README の「サービスを使う章」）")
    with psycopg.connect(os.environ["PG_DSN"], autocommit=True) as con:
        con.execute(CREATE_TABLE)
        n = replace_day(con, day, Path("work/out/daily_sales") / f"date={day}.csv")
    print(f"{day}: {n} 行を b12.daily_sales に入れました")
