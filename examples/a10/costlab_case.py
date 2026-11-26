"""ケーススタディ: ダッシュボードの読み取りを減らし、月額の内訳がどう動くかを見ます。"""
import tempfile
from pathlib import Path

from costlab_files import compact
from costlab_guard import estimate_scan, parquet_files
from costlab_layouts import connect, files_and_bytes, make_events, write_layouts
from costlab_meter import measure
from costlab_model import Rates, monthly_cost
from costlab_querylog import QueryLog

W = "event_date BETWEEN '2026-03-01' AND '2026-03-07'"
GB = 1e9


def workload(src):
    """利用者ごとのクエリ。(タグ, SQL, 1 日の回数) の並びです。src は FROM に入れる読み取り式。"""
    return [
        ("dashboard", f"SELECT event_type, sum(amount) FROM {src} WHERE {W} GROUP BY event_type", 100),
        ("analyst_star", f"SELECT * FROM {src} WHERE {W}", 5),
        ("weekly_report", f"SELECT customer_id, sum(amount) FROM {src} GROUP BY customer_id", 1),
    ]


def daily_ranking(con, src):
    log = QueryLog()
    for tag, sql, runs in workload(src):
        log.record(con, tag, sql, runs)
    return log.ranking()


def scale_check(sizes=(250_000, 1_000_000, 4_000_000)):
    """行数を増やしたとき、ダッシュボードの 1 回の読み取りバイトがどう増えるか (flat と、日付順の 1 ファイル)。"""
    out = {}
    for n in sizes:
        con = connect()
        make_events(con, n)
        with tempfile.TemporaryDirectory() as d:
            con.execute(f"COPY events TO '{d}/flat.parquet' (FORMAT parquet)")
            con.execute(f"COPY (SELECT * FROM events ORDER BY event_date) TO '{d}/sorted.parquet' "
                        "(FORMAT parquet, ROW_GROUP_SIZE 50000)")
            out[n] = tuple(measure(con, workload(f"read_parquet('{d}/{name}.parquet')")[0][1])["read_bytes"]
                           for name in ("flat", "sorted"))
    return out


def request_cost(root, runs_per_day=100):
    """ダッシュボード 1 回のリクエスト数を、daily 365 ファイルと まとめ直した 3 ファイルで見積もり、月額 (仮の単価) にします。"""
    columns = ["event_type", "amount", "event_date"]
    daily = estimate_scan(parquet_files(f"{root}/daily"), columns, "2026-03-01", "2026-03-07")[1]
    compacted = estimate_scan(parquet_files(f"{root}/after"), columns, "2026-03-01", "2026-03-07")[1]
    per_month = {name: monthly_cost(Rates(), storage_gb=0, scan_tb=0, egress_gb=0, requests=n * runs_per_day * 30,
                                    compute_hours=0)["total"] for name, n in (("daily", daily), ("compacted", compacted))}
    return {"daily": daily, "compacted": compacted, "monthly": per_month}


def before_after(root, scale=1000):
    """flat と、まとめ直して日付順にした置き方で、月額の内訳を比べます (行数を scale 倍した想定)。"""
    con = connect()
    make_events(con)
    root = Path(root)
    write_layouts(con, root)
    compact(con, f"{root}/daily/*/*.parquet", f"{root}/after")
    layouts = {"before": (f"read_parquet('{root}/flat.parquet')", files_and_bytes(root / "flat.parquet")),
               "after": (f"read_parquet('{root}/after/*.parquet')", files_and_bytes(root / "after"))}
    result = {}
    for name, (src, (files, stored)) in layouts.items():
        ranking = daily_ranking(con, src)
        scan_tb = sum(r[1] for r in ranking) * 30 * scale / 1e12
        cost = monthly_cost(Rates(), storage_gb=stored * scale / GB, scan_tb=scan_tb,
                            egress_gb=0, requests=0, compute_hours=0)
        result[name] = {"files": files, "stored": stored, "ranking": ranking, "scan_tb": scan_tb, "cost": cost}
    return result
