"""第10章の出力をこの順に出します: 置き方・LIMIT・小さなファイル・圧縮・事前集計・外に出す量・止め忘れ・ケーススタディ。"""
import tempfile
from pathlib import Path

from costlab_agg import build_daily_agg, dashboard_bytes
from costlab_case import before_after, request_cost, scale_check
from costlab_egress import export_sizes
from costlab_files import codec_report, compact
from costlab_guard import check_budget, estimate_scan, parquet_files
from costlab_layouts import N_ROWS, column_bytes, connect, files_and_bytes, make_events, write_layouts
from costlab_limit import footer_report, limit_report, row_group_effect
from costlab_meter import mb, measure
from costlab_model import billed_minutes, query_starts
from costlab_prune import prune_report
from costlab_sensitivity import sensitivity_rows
from costlab_twocols import two_column_report


def main():
    con = connect()
    make_events(con)
    print(f"events: {N_ROWS:,} 行")
    with tempfile.TemporaryDirectory() as d:
        write_layouts(con, d)
        print("\n== 置き方ごとの保存サイズ ==")
        for name in ("flat.parquet", "sorted.parquet", "monthly", "daily"):
            files, size = files_and_bytes(Path(d) / name)
            print(f"{name:15} files={files:3}  bytes={size:,}")

        print("\n== 列ごとの圧縮後バイト数 ==")
        for name in ("flat.parquet", "sorted.parquet"):
            cb = column_bytes(Path(d) / name)
            print(f"{name:15} event_id={mb(cb['event_id']):>9}  event_date={mb(cb['event_date']):>9}  "
                  f"customer_id={mb(cb['customer_id']):>9}  amount={mb(cb['amount']):>9}  payload={mb(cb['payload']):>9}")
        small, default = row_group_effect(con, d)
        print(f"日付順で amount の行グループ: 5 万行 {mb(small)} / 既定 {mb(default)}")

        print("\n== 3 月第 1 週の sum(amount) が読んだバイト数 ==")
        base = None
        for r in prune_report(con, d):
            base = base or r["seconds"]
            print(f"{r['layout']:20} read={mb(r['read_bytes']):>10}  取り出し={r['files_opened']:3}  秒の比={r['seconds'] / base:5.2f}")

        print("\n== 列を絞る・LIMIT をつける (flat) ==")
        src = f"read_parquet('{d}/flat.parquet')"
        for label, sql in [("sum(amount)", f"SELECT sum(amount) FROM {src}"),
                           ("event_type, amount", f"SELECT event_type, amount FROM {src}"),
                           ("SELECT *", f"SELECT * FROM {src}"),
                           ("SELECT * LIMIT 10", f"SELECT * FROM {src} LIMIT 10")]:
            print(f"{label:20} read={mb(measure(con, sql)['read_bytes']):>10}")

        print("\n== LIMIT 10 と行グループの大きさ ==")
        for size, (groups, read, per_group) in limit_report(con, d).items():
            print(f"行グループ {size:>7,} 行 ({groups:3} 個): read={mb(read):>9}  = 行グループ {per_group:.1f} 個分")

        print("\n== 小さなファイル: daily 365 個 → まとめ直し ==")
        files, size = compact(con, f"{d}/daily/*/*.parquet", f"{d}/compacted")
        print(f"compacted files={files} bytes={size:,}")
        mean_footer, n_files = footer_report(parquet_files(f"{d}/daily"))
        print(f"daily のフッター: 平均 {mean_footer:,.0f} バイト ({n_files} ファイル)")
        full_daily = measure(con, f"SELECT sum(amount) FROM read_parquet('{d}/daily/*/*.parquet')")
        full_comp = measure(con, f"SELECT sum(amount) FROM read_parquet('{d}/compacted/*.parquet')")
        print(f"全件の sum(amount): daily read={mb(full_daily['read_bytes'])}  compacted read={mb(full_comp['read_bytes'])}")
        print(f"秒の比 daily / compacted = 約 {round(full_daily['seconds'] / full_comp['seconds'])} 倍")

        print("\n== 見積り (dry-run) と実測 ==")
        for name, path in (("flat", f"{d}/flat.parquet"), ("sorted", f"{d}/sorted.parquet")):
            est, requests = estimate_scan(parquet_files(path), ["amount", "event_date"], "2026-03-01", "2026-03-07")
            actual = measure(con, f"SELECT sum(amount) FROM read_parquet('{path}') WHERE event_date "
                                  "BETWEEN '2026-03-01' AND '2026-03-07'")["read_bytes"]
            print(f"{name:7} 見積り={mb(est):>9} (リクエスト {requests:3})  実測={mb(actual):>9}")
        try:
            check_budget(parquet_files(f"{d}/flat.parquet"), ["amount", "event_date"], "2026-03-01", "2026-03-07", 1_000_000)
        except RuntimeError as e:
            print("上限 1.00 MB で拒否:", e)

        print("\n== 絞る列が 2 つ ==")
        for (layout, label), nbytes in two_column_report(con, d).items():
            print(f"{layout:8} {label:10} read={mb(nbytes):>9}")

        print("\n== 圧縮方式 ==")
        report = codec_report(con, d)
        for codec, m in report.items():
            print(f"{codec:13} bytes={m['bytes']:>11,}  書く秒の比={m['write_s'] / report['uncompressed']['write_s']:.1f}  "
                  f"読む秒の比={m['read_s'] / report['uncompressed']['read_s']:.1f}")

        print("\n== 事前集計 ==")
        agg = build_daily_agg(con, d)
        raw, small = dashboard_bytes(con, f"read_parquet('{d}/flat.parquet')", agg)
        rows = con.execute(f"SELECT count(*) FROM read_parquet('{agg}')").fetchone()[0]
        print(f"集計表 {rows:,} 行 ({Path(agg).stat().st_size:,} バイト)  ダッシュボード: 元の表 {mb(raw)} / 集計表 {mb(small)}")

        print("\n== 外に出すデータの大きさ (3 月第 1 週) ==")
        for name, size in export_sizes(con, d).items():
            print(f"{name:16} {size:>10,}")

    print("\n== 使っていない計算資源 (平日 22 日分の模型) ==")
    starts = query_starts()
    print(f"クエリ {len(starts)} 回")
    for wait in (None, 240, 60, 10, 1):
        minutes = billed_minutes(starts, suspend_after=wait)
        print(f"停止までの待ち={str(wait) + ' 分' if wait else '止めない':8}  課金 {minutes:6,} 分 ({minutes / 60:6.1f} 時間)")

    print("\n== ケーススタディ ==")
    checked = scale_check()
    first = checked[min(checked)]
    for n, (flat, srt) in checked.items():
        print(f"{n:>9,} 行: flat {mb(flat)} ({flat / first[0]:.1f} 倍)  日付順 {mb(srt)} ({srt / first[1]:.1f} 倍)")
    with tempfile.TemporaryDirectory() as d:
        result = before_after(d)
        requests = request_cost(d)
    for name in ("before", "after"):
        r = result[name]
        print(f"[{name}] files={r['files']} stored={r['stored']:,}")
        for tag, nbytes, share in r["ranking"]:
            print(f"  {tag:14} 1日 {mb(nbytes):>11} ({share}%)")
        parts = r["cost"]["parts"]
        print(f"  月額(仮の単価, 1000 倍): scan={parts['scan']:.2f} storage={parts['storage']:.2f} total={r['cost']['total']:.2f}")
    print(f"リクエスト見積り (ダッシュボード 1 回): daily {requests['daily']} / まとめ直し後 {requests['compacted']}")
    print(f"リクエストの月額 (仮の単価, 1 日 100 回): daily {requests['monthly']['daily']:.4f} / まとめ直し後 {requests['monthly']['compacted']:.4f}")
    print("単価の感度 (保存の単価の倍率, スキャンの単価の倍率, 変更前, 変更後):")
    for row in sensitivity_rows(result):
        print("  ", " / ".join(row))


if __name__ == "__main__":
    main()
