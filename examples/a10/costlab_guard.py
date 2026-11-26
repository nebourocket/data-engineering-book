"""実行前の見積り (dry-run): Parquet のフッターだけから、読むバイト数とリクエスト数を見積もります。"""
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq


def estimate_scan(files, columns, lo, hi):
    """event_date が lo〜hi の行グループだけを読むとして、列 columns の圧縮後バイト数の合計と、
    リクエスト数 (ファイルごとにフッター 1 回 + 読む行グループ × 列) を返します。"""
    lo, hi = date.fromisoformat(lo), date.fromisoformat(hi)
    total_bytes, requests = 0, 0
    for f in files:
        meta = pq.ParquetFile(f).metadata
        names = [meta.row_group(0).column(i).path_in_schema for i in range(meta.num_columns)]
        requests += 1
        for g in range(meta.num_row_groups):
            rg = meta.row_group(g)
            stats = rg.column(names.index("event_date")).statistics
            if stats.max < lo or stats.min > hi:
                continue
            for name in columns:
                total_bytes += rg.column(names.index(name)).total_compressed_size
                requests += 1
    return total_bytes, requests


def check_budget(files, columns, lo, hi, limit_bytes):
    """見積りが上限 (バイト) を超えるなら、流す前に止めます (BigQuery の maximum bytes billed と同じ発想)。"""
    estimated, _ = estimate_scan(files, columns, lo, hi)
    if estimated > limit_bytes:
        raise RuntimeError(f"見積り {estimated:,} バイトが上限 {limit_bytes:,} バイトを超えます")
    return estimated


def parquet_files(path):
    path = Path(path)
    return [path] if path.is_file() else sorted(path.rglob("*.parquet"))
