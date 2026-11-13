"""第 11 章: work/sales を sales ビューとして開き、queries.sql の名前付きクエリを 1 つ流します。

使い方: python examples/b11/run_query.py explain_month
（先に python examples/b11/partition_demo.py で work/sales を作っておきます）
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from partition_demo import open_sales, scan_stats, split_queries  # noqa: E402

if __name__ == "__main__":
    name = sys.argv[1]
    sql = split_queries((HERE / "queries.sql").read_text(encoding="utf-8"))[name]
    con = open_sales(Path("work/sales"))
    if name.startswith("explain"):
        print(con.execute(sql).fetchall()[0][1])  # 計画は 2 列目の 1 つの文字列に入っている
    else:
        con.sql(sql).show(max_width=200)
        print(scan_stats(con, sql))  # 開いたファイル数と読んだバイト数
