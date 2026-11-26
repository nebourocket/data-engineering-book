"""LIMIT が読むバイト数と、フッターの大きさを測ります。"""
import os
import statistics

import pyarrow.parquet as pq

from costlab_layouts import column_bytes
from costlab_meter import measure


def limit_report(con, root, sizes=(122880, 20000, 5000)):
    """行グループの大きさを変えて書き、SELECT * LIMIT 10 の読み取りを測ります。(行グループ数, 読み取りバイト, 読み取り ÷ 1 行グループの平均バイト)。"""
    out = {}
    for size in sizes:
        path = f"{root}/rg{size}.parquet"
        con.execute(f"COPY events TO '{path}' (FORMAT parquet, ROW_GROUP_SIZE {size})")
        groups = pq.ParquetFile(path).metadata.num_row_groups
        read = measure(con, f"SELECT * FROM read_parquet('{path}') LIMIT 10")["read_bytes"]
        out[size] = (groups, read, read / (os.path.getsize(path) / groups))
    return out


def footer_report(files):
    """Parquet のフッター (メタデータ) の大きさ: (平均バイト, ファイル数)。"""
    sizes = [pq.ParquetFile(f).metadata.serialized_size for f in files]
    return statistics.mean(sizes), len(sizes)


def row_group_effect(con, root):
    """日付順に並べた表で、行グループを 5 万行と既定 (122,880 行) にしたときの amount 列の圧縮後バイト数。"""
    con.execute(f"COPY (SELECT * FROM events ORDER BY event_date) TO '{root}/sorted_default_rg.parquet' (FORMAT parquet)")
    return (column_bytes(f"{root}/sorted.parquet")["amount"], column_bytes(f"{root}/sorted_default_rg.parquet")["amount"])
