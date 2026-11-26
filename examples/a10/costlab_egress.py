"""外へ出すデータの大きさ: 何を出すかでバイト数がどう変わるか。"""
from pathlib import Path

W = "event_date BETWEEN '2026-03-01' AND '2026-03-07'"


def export_sizes(con, root):
    """3 月第 1 週のデータを 3 通りの形で書き出し、ファイルの大きさを返します。"""
    root = Path(root)
    con.execute(f"COPY (SELECT * FROM events WHERE {W}) TO '{root}/week.csv' (FORMAT csv, HEADER)")
    con.execute(f"COPY (SELECT * FROM events WHERE {W}) TO '{root}/week.parquet' (FORMAT parquet, COMPRESSION zstd)")
    con.execute(f"COPY (SELECT event_date, event_type, count(*) AS n, sum(amount) AS amount FROM events WHERE {W} "
                f"GROUP BY ALL) TO '{root}/week_agg.parquet' (FORMAT parquet, COMPRESSION zstd)")
    return {name: (root / name).stat().st_size for name in ("week.csv", "week.parquet", "week_agg.parquet")}
