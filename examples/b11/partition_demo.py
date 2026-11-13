"""第 11 章: 月ごとに分けた Parquet を DuckDB で読み、パーティション・プルーニングの効果を測ります。

使い方: python examples/b11/partition_demo.py
work/sales/month=2026-03/data_0.parquet のような Hive 形式のフォルダを作り、
4 通りのクエリの EXPLAIN ANALYZE から「開いたファイル数」と「読んだバイト数」を表示します。
"""
import re
import sys
from pathlib import Path

import duckdb
import pyarrow as pa

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from neboske_shop import generate  # noqa: E402

SEEDS = range(1, 21)  # 20 通りの seed を重ねて約 15 万行にします（1 回分では小さすぎて差が見えません）

UNITS = {"B": 1, "kB": 1_000, "MB": 1_000_000, "GB": 1_000_000_000}


def sales_lines(seeds=SEEDS) -> list[dict]:
    """注文と明細をつないだ「1 行 = 1 明細」の売上を作ります。order_id は seed ごとにずらして重ならないようにします。"""
    rows = []
    for k, seed in enumerate(seeds):
        data = generate(seed)
        orders = {o["order_id"]: o for o in data["orders"]}
        for i in data["order_items"]:
            o = orders[i["order_id"]]
            rows.append({
                "order_id": o["order_id"] + 10_000 * k, "line_no": i["line_no"],
                "customer_id": o["customer_id"], "ordered_at": o["ordered_at"], "status": o["status"],
                "product_id": i["product_id"], "quantity": i["quantity"], "unit_price": i["unit_price"]})
    return rows


def write_partitioned(root: Path, rows: list[dict]) -> None:
    """month 列（'2026-03' の形）の値ごとに、root/month=2026-03/ というフォルダへ書き分けます。"""
    root.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("t", pa.Table.from_pylist(rows))
    con.execute("""
        CREATE TABLE s AS
        SELECT *, strftime(CAST(ordered_at AS TIMESTAMP), '%Y-%m') AS month FROM t""")
    con.execute(f"COPY s TO '{root}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (month), OVERWRITE_OR_IGNORE)")
    con.close()


def open_sales(root: Path) -> duckdb.DuckDBPyConnection:
    """Hive 形式のフォルダ全体を、sales という 1 つのビューとして開きます。"""
    con = duckdb.connect()
    con.execute(f"CREATE VIEW sales AS SELECT * FROM read_parquet('{root}/*/*.parquet', hive_partitioning = true)")
    return con


def scan_stats(con: duckdb.DuckDBPyConnection, sql: str) -> dict:
    """EXPLAIN ANALYZE の出力から、開いたファイル数と読んだバイト数を取り出します（DuckDB 2.0 の出力形式）。"""
    plan = con.execute("EXPLAIN ANALYZE " + sql).fetchall()[0][1]
    read = int(re.search(r"Total Files Read: (\d+)", plan).group(1))
    value, unit = re.search(r"Data Read:\s+([\d.]+) (B|kB|MB|GB)", plan).groups()
    return {"files_read": read, "bytes_read": round(float(value) * UNITS[unit])}


def split_queries(text: str) -> dict[str, str]:
    """「-- name: 名前」で区切って {名前: SQL} を返します（第 5 章の run_sql.py と同じ決まりです）。"""
    parts = re.split(r"^-- name: (\S+)\n", text, flags=re.M)
    return {name: sql.strip().rstrip(";") for name, sql in zip(parts[1::2], parts[2::2])}


def run_scenarios(root: Path) -> list[dict]:
    queries = split_queries((HERE / "queries.sql").read_text(encoding="utf-8"))
    con = open_sales(root)
    results = []
    for name in ("full_scan", "month_filter", "date_filter_only", "select_star"):
        results.append({"name": name, **scan_stats(con, queries[name])})
    con.close()
    return results


if __name__ == "__main__":
    root = Path("work/sales")
    write_partitioned(root, sales_lines())
    print(f"files: {len(list(root.glob('*/*.parquet')))}")
    for r in run_scenarios(root):
        print(f"{r['name']:<18} files_read={r['files_read']}  bytes_read={r['bytes_read']:,}")
