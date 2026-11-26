"""削除の要求と Parquet: 置き方によって、1 人を消すのに書き直すファイルの数が変わります。"""
from pathlib import Path

import duckdb

from govlab_data import load_shop


def build(root):
    """注文(明細つき)を、月ごと / 顧客番号の剰余 16 通り の 2 通りで書き、DuckDB の接続とルートを返します。"""
    root = Path(root)
    _, orders = load_shop()
    con = duckdb.connect()
    con.execute("PRAGMA threads=1")  # 書き出しの順を固定し、バイト数を毎回同じにする
    con.execute("CREATE TABLE o (order_id INTEGER, customer_id INTEGER, ordered_at VARCHAR, status VARCHAR, note VARCHAR)")
    con.executemany("INSERT INTO o VALUES (?, ?, ?, ?, ?)",
                    [(x["order_id"], x["customer_id"], x["ordered_at"], x["status"], x["note"]) for x in orders])
    con.execute(f"COPY (SELECT *, substr(ordered_at, 1, 7) AS month FROM o) TO '{root}/by_month' "
                "(FORMAT parquet, PARTITION_BY (month))")
    con.execute(f"COPY (SELECT *, customer_id % 16 AS bucket FROM o) TO '{root}/by_customer' "
                "(FORMAT parquet, PARTITION_BY (bucket))")
    return con, root


def touched(con, folder, customer_id):
    """customer_id の行を含むファイルの (数, 全ファイル数, そのバイト数, 全バイト数)。"""
    files = sorted(Path(folder).rglob("*.parquet"))
    hit = [f for f in files if con.execute(
        f"SELECT count(*) FROM read_parquet('{f}', hive_partitioning=false) WHERE customer_id = ?", [customer_id]).fetchone()[0]]
    return len(hit), len(files), sum(f.stat().st_size for f in hit), sum(f.stat().st_size for f in files)


def erase(con, folder, customer_id):
    """その顧客の行を含むファイルだけを、行を除いて書き直します。書き直したファイル数を返します。"""
    rewritten = 0
    for f in sorted(Path(folder).rglob("*.parquet")):
        n = con.execute(f"SELECT count(*) FROM read_parquet('{f}', hive_partitioning=false) WHERE customer_id = ?", [customer_id]).fetchone()[0]
        if n:
            tmp = f.with_suffix(".tmp")
            con.execute(f"COPY (SELECT * FROM read_parquet('{f}', hive_partitioning=false) WHERE customer_id <> {int(customer_id)}) "
                        f"TO '{tmp}' (FORMAT parquet)")
            tmp.replace(f)
            rewritten += 1
    return rewritten


def files_per_customer(con):
    """月ごとの置き方で、1 人の注文が散らばる月 (= ファイル) の数の (平均, 最大)。顧客番号の置き方は常に 1 です。"""
    avg, most = con.execute(
        "SELECT round(avg(n), 2), max(n) FROM "
        "(SELECT customer_id, count(DISTINCT substr(ordered_at, 1, 7)) AS n FROM o GROUP BY customer_id)").fetchone()
    return avg, most
