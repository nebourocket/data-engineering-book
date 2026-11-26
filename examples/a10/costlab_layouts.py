"""同じイベント表を、置き方の違う Parquet に書き分けます (第10章)。"""
from pathlib import Path

import duckdb

N_ROWS = 1_000_000  # 100 万行 (1 日あたり約 2,700 行 × 365 日)

EVENTS_SQL = """
SELECT i AS event_id,
       hash(i) % 50000 AS customer_id,
       DATE '2026-01-01' + CAST(hash(i * 7) % 365 AS INTEGER) AS event_date,
       CASE hash(i * 5) % 4 WHEN 0 THEN 'view' WHEN 1 THEN 'search' WHEN 2 THEN 'add_to_cart' ELSE 'purchase' END AS event_type,
       (hash(i * 3) % 10000) / 100.0 AS amount,
       md5(CAST(i AS VARCHAR)) || md5(CAST(i * 7919 + 1 AS VARCHAR)) AS payload
FROM range({n}) t(i)
"""


def connect():
    """1 スレッドの DuckDB。読んだバイト数を毎回同じにするためです。"""
    con = duckdb.connect()
    con.execute("PRAGMA threads=1")
    return con


def make_events(con, n=N_ROWS):
    """日付が行の並びと無関係にばらつく (= 並べ替えていない) イベント表を作ります。"""
    con.execute("CREATE OR REPLACE TABLE events AS " + EVENTS_SQL.format(n=n))


def write_layouts(con, root):
    """flat (1 ファイル) / sorted (日付順) / monthly (月ごと) / daily (日ごと) の 4 通りで書きます。"""
    root = Path(root)
    con.execute(f"COPY events TO '{root}/flat.parquet' (FORMAT parquet)")
    con.execute(f"COPY (SELECT * FROM events ORDER BY event_date) TO '{root}/sorted.parquet' "
                "(FORMAT parquet, ROW_GROUP_SIZE 50000)")
    con.execute(f"COPY (SELECT *, strftime(event_date, '%Y-%m') AS month FROM events) TO '{root}/monthly' "
                "(FORMAT parquet, PARTITION_BY (month))")
    con.execute(f"COPY (SELECT *, event_date AS day FROM events) TO '{root}/daily' "
                "(FORMAT parquet, PARTITION_BY (day))")


def files_and_bytes(path):
    """パス (ファイルまたはフォルダ) の下の Parquet の数と合計バイト数。"""
    path = Path(path)
    files = [path] if path.is_file() else sorted(path.rglob("*.parquet"))
    return len(files), sum(f.stat().st_size for f in files)


def column_bytes(path):
    """Parquet ファイルの列ごとの圧縮後バイト数 (全行グループの合計)。pyarrow がフッターから読みます。"""
    import pyarrow.parquet as pq

    meta = pq.ParquetFile(path).metadata
    sizes = {}
    for g in range(meta.num_row_groups):
        for c in range(meta.num_columns):
            col = meta.row_group(g).column(c)
            sizes[col.path_in_schema] = sizes.get(col.path_in_schema, 0) + col.total_compressed_size
    return sizes
