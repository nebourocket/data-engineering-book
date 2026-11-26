"""置き方 (レイアウト) ごとに、同じ「3 月第 1 週の合計」が何バイト読むかを測ります。"""
from costlab_meter import measure

WEEK = "event_date BETWEEN '2026-03-01' AND '2026-03-07'"


def cases(root):
    """(名前, 読み取り式, 追加の条件) の一覧。追加の条件はパーティション列への条件です。"""
    return [
        ("flat", f"read_parquet('{root}/flat.parquet')", ""),
        ("sorted", f"read_parquet('{root}/sorted.parquet')", ""),
        ("monthly (日付だけ)", f"read_parquet('{root}/monthly/*/*.parquet', hive_partitioning=true)", ""),
        ("monthly (月も指定)", f"read_parquet('{root}/monthly/*/*.parquet', hive_partitioning=true)", "AND month = '2026-03'"),
        ("daily (日付だけ)", f"read_parquet('{root}/daily/*/*.parquet', hive_partitioning=true)", ""),
        ("daily (日も指定)", f"read_parquet('{root}/daily/*/*.parquet', hive_partitioning=true)",
         "AND day BETWEEN '2026-03-01' AND '2026-03-07'"),
    ]


def prune_report(con, root):
    """読み取りバイト数・開いたファイル数・最短秒を、置き方ごとに返します。"""
    rows = []
    for name, src, extra in cases(root):
        m = measure(con, f"SELECT sum(amount) FROM {src} WHERE {WEEK} {extra}")
        opened = con.execute(
            f"SELECT count(DISTINCT filename) FROM {src.replace(')', ', filename=true)')} WHERE {WEEK} {extra}"
        ).fetchone()[0]
        rows.append({"layout": name, "read_bytes": m["read_bytes"], "files_opened": opened, "seconds": m["seconds"]})
    return rows
