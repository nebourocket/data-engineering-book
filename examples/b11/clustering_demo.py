"""第 11 章: 同じ行を「ばらばら」と「customer_id 順」で Parquet に書き、行グループの読み飛ばしを比べます。

使い方: python examples/b11/clustering_demo.py
行グループ（Parquet が最小値・最大値を持つ単位）を 10,000 行にして、customer_id = 42 の件数を数えます。
"""
import re
import sys
from pathlib import Path

import duckdb
import pyarrow as pa

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from partition_demo import UNITS, sales_lines  # noqa: E402

ROW_GROUP = 10_000
QUERY = "SELECT count(*) FROM read_parquet('{path}') WHERE {column} = {value}"


def write_both(workdir: Path) -> dict[str, Path]:
    """同じ行を、並べ方だけ変えて 2 つのファイルに書きます（random() は並べ替えの乱数です）。"""
    workdir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("t", pa.Table.from_pylist(sales_lines()))
    paths = {"ばらばら": workdir / "shuffled.parquet", "customer_id 順": workdir / "sorted.parquet"}
    orders = {"ばらばら": "random()", "customer_id 順": "customer_id"}
    for label, path in paths.items():
        con.execute(f"COPY (SELECT * FROM t ORDER BY {orders[label]}) TO '{path}' "
                    f"(FORMAT parquet, ROW_GROUP_SIZE {ROW_GROUP})")
    con.close()
    return paths


def row_groups_scanned(path: Path, column: str = "customer_id", value: int = 42) -> dict:
    """EXPLAIN ANALYZE から、読んだ行グループの数と読んだバイト数を取り出します。"""
    con = duckdb.connect()
    plan = con.execute("EXPLAIN ANALYZE " + QUERY.format(path=path, column=column, value=value)).fetchall()[0][1]
    scanned, total = re.search(r"Row Groups Scanned: (\d+) / (\d+)", plan).groups()
    value, unit = re.search(r"Data Read:\s+([\d.]+) (B|kB|MB|GB)", plan).groups()
    return {"scanned": int(scanned), "total": int(total), "bytes_read": round(float(value) * UNITS[unit])}


if __name__ == "__main__":
    for label, path in write_both(Path("work/cluster")).items():
        r = row_groups_scanned(path)
        print(f"{label:<14} 行グループ {r['scanned']} / {r['total']}  読んだバイト数 {r['bytes_read']:,}")
