"""同じ売上明細を CSV / JSON Lines / Parquet で書き出し、サイズと読み込み時間を測ります。

ねぼすけ商店のデータを seed を変えて何度も作り、つなげて十数万行〜数十万行にします
（1 回分だけだと小さすぎて差が見えないためです）。時間は 1 回ごとに新しい接続で測り、
3 回のうち最短を取ります。ファイルは OS のキャッシュに載った状態（ウォーム）です。
"""
import gzip
import shutil
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.common.neboske_shop import generate  # noqa: E402


def build_table(seeds: int = 60) -> pa.Table:
    """注文・明細・商品・顧客を結合した平らな売上明細を作ります。"""
    rows = []
    for seed in range(seeds):
        d = generate(seed)
        orders = {o["order_id"]: o for o in d["orders"]}
        products = {p["product_id"]: p for p in d["products"]}
        customers = {c["customer_id"]: c for c in d["customers"]}
        for it in d["order_items"]:
            o = orders[it["order_id"]]
            p = products[it["product_id"]]
            c = customers[o["customer_id"]]
            rows.append({
                "order_id": seed * 10_000 + it["order_id"], "line_no": it["line_no"],
                "ordered_at": o["ordered_at"], "status": o["status"],
                "customer_id": o["customer_id"], "prefecture": c["prefecture"],
                "product_id": it["product_id"], "product_name": p["name"],
                "category": p["category"], "quantity": it["quantity"],
                "unit_price": it["unit_price"]})
    return pa.Table.from_pylist(rows)


def write_files(table: pa.Table, out: Path) -> dict[str, Path]:
    """4 通りの形式で書き出し、名前 → パスの dict を返します。"""
    con = duckdb.connect()
    con.register("t", table)
    paths = {
        "CSV": out / "sales.csv",
        "CSV (gzip)": out / "sales.csv.gz",
        "JSON Lines": out / "sales.jsonl",
        "Parquet (snappy)": out / "sales_snappy.parquet",
        "Parquet (zstd)": out / "sales_zstd.parquet",
    }
    con.execute(f"COPY t TO '{paths['CSV']}' (FORMAT csv, HEADER)")
    with open(paths["CSV"], "rb") as src, gzip.open(paths["CSV (gzip)"], "wb") as dst:
        shutil.copyfileobj(src, dst)
    con.execute(f"COPY t TO '{paths['JSON Lines']}' (FORMAT json)")
    con.execute(f"COPY t TO '{paths['Parquet (snappy)']}' (FORMAT parquet, COMPRESSION snappy)")
    con.execute(f"COPY t TO '{paths['Parquet (zstd)']}' (FORMAT parquet, COMPRESSION zstd)")
    con.close()
    return paths


def reader(path: Path) -> str:
    """拡張子から DuckDB の読み込み関数を選びます。"""
    name = path.name
    if name.endswith((".csv", ".csv.gz")):
        return f"read_csv('{path}')"
    if name.endswith(".jsonl"):
        return f"read_json('{path}')"
    return f"read_parquet('{path}')"


def best_of(sql: str, repeat: int = 3) -> float:
    """新しい接続で sql を repeat 回流し、最短の秒数を返します。"""
    times = []
    for _ in range(repeat):
        con = duckdb.connect()
        t0 = time.perf_counter()
        con.execute(sql).fetchall()
        times.append(time.perf_counter() - t0)
        con.close()
    return min(times)


def measure(seeds: int = 60) -> list[dict]:
    """形式ごとにサイズ・全列の読み込み時間・1 列だけの集計時間を測ります。"""
    table = build_table(seeds)
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, path in write_files(table, Path(tmp)).items():
            src = reader(path)
            results.append({
                "format": name,
                "rows": table.num_rows,
                "size_mb": path.stat().st_size / 1_000_000,
                # 全列を読み込んでテーブルにする
                "load_all_s": best_of(f"CREATE TABLE t AS SELECT * FROM {src}"),
                # 1 列だけ使う集計
                "sum_one_col_s": best_of(f"SELECT sum(unit_price) FROM {src}"),
            })
    return results


if __name__ == "__main__":
    for r in measure():
        print(f"{r['format']:<18} {r['size_mb']:7.1f} MB  load_all {r['load_all_s']:.3f} s  "
              f"sum_one_col {r['sum_one_col_s']:.3f} s  ({r['rows']:,} rows)")
