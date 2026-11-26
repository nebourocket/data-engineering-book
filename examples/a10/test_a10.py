"""第10章のコードの検査。本文の数字を固定します。読んだバイト数は先読みで揺れるので near() の幅 (既定 ±5%) を持たせます。"""
import csv
from pathlib import Path

import pytest

from costlab_agg import build_daily_agg, dashboard_bytes
from costlab_case import before_after, request_cost, scale_check
from costlab_egress import export_sizes
from costlab_files import codec_report, compact
from costlab_layouts import N_ROWS, column_bytes, connect, files_and_bytes, make_events, write_layouts
from costlab_guard import check_budget, estimate_scan, parquet_files
from costlab_limit import footer_report, limit_report, row_group_effect
from costlab_meter import mb, measure
from costlab_sensitivity import sensitivity_rows
from costlab_twocols import two_column_report
from costlab_model import Rates, billed_minutes, monthly_cost, query_starts
from costlab_prune import prune_report


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    root = tmp_path_factory.mktemp("lab")
    con = connect()
    make_events(con)
    write_layouts(con, root)
    return con, root


def near(actual, expected_mb, tolerance=0.05):
    """読んだバイト数 (バイト) が、本文の MB の値の ±5 % に入っているか。"""
    return abs(actual / 1e6 - expected_mb) <= expected_mb * tolerance


def test_layout_sizes_and_file_counts(lab):
    _, root = lab
    assert N_ROWS == 1_000_000
    assert files_and_bytes(root / "flat.parquet") == (1, 77_619_672)
    assert files_and_bytes(root / "sorted.parquet") == (1, 78_016_666)
    assert files_and_bytes(root / "monthly") == (12, 77_516_870)
    assert files_and_bytes(root / "daily") == (365, 80_223_568)


def test_sorting_changes_which_columns_compress(lab):
    _, root = lab
    flat, srt = column_bytes(root / "flat.parquet"), column_bytes(root / "sorted.parquet")
    assert near(flat["event_id"], 4.00) and near(srt["event_id"], 4.79)
    assert near(flat["event_date"], 1.14) and srt["event_date"] < 5_000  # 日付順なら、同じ値の連続 1 つで済む
    assert near(flat["payload"], 65.69) and near(srt["payload"], 65.70)


def test_pruning_reads_far_less_when_layout_matches_the_filter(lab):
    con, root = lab
    r = {x["layout"]: x for x in prune_report(con, str(root))}
    assert near(r["flat"]["read_bytes"], 3.46)
    assert near(r["sorted"]["read_bytes"], 0.28)
    assert near(r["monthly (日付だけ)"]["read_bytes"], 0.45)
    assert near(r["monthly (月も指定)"]["read_bytes"], 0.28)
    assert near(r["daily (日付だけ)"]["read_bytes"], 6.08)
    assert near(r["daily (日も指定)"]["read_bytes"], 0.23)
    assert [r[k]["files_opened"] for k in ("flat", "sorted", "monthly (日付だけ)", "daily (日付だけ)")] == [1, 1, 1, 7]
    # 日ごとに割りすぎると、パーティションを絞っても 365 個のフッターを読む分だけ flat より重くなる
    assert r["daily (日付だけ)"]["read_bytes"] > r["flat"]["read_bytes"]


def test_column_pruning_and_limit(lab):
    con, root = lab
    src = f"read_parquet('{root}/flat.parquet')"
    assert near(measure(con, f"SELECT sum(amount) FROM {src}")["read_bytes"], 2.31)
    assert near(measure(con, f"SELECT event_type, amount FROM {src}")["read_bytes"], 2.57)
    assert near(measure(con, f"SELECT * FROM {src}")["read_bytes"], 77.61)
    assert near(measure(con, f"SELECT * FROM {src} LIMIT 10")["read_bytes"], 38.18)


def test_compaction_cuts_footer_reads(lab):
    con, root = lab
    assert compact(con, f"{root}/daily/*/*.parquet", root / "compacted")[0] == 3
    assert files_and_bytes(root / "compacted") == (3, 78_041_890)
    daily = measure(con, f"SELECT sum(amount) FROM read_parquet('{root}/daily/*/*.parquet')")
    comp = measure(con, f"SELECT sum(amount) FROM read_parquet('{root}/compacted/*.parquet')")
    assert near(daily["read_bytes"], 10.70) and near(comp["read_bytes"], 2.82)
    assert daily["seconds"] > 3 * comp["seconds"]  # 本文では約 6 倍 (5〜7 倍で揺れる)。下限だけ


def test_codec_sizes(lab):
    con, root = lab
    sizes = {k: v["bytes"] for k, v in codec_report(con, root).items()}
    assert sizes == {"uncompressed": 88_042_505, "snappy": 77_619_672, "zstd": 42_618_727}


def test_export_sizes(lab):
    con, root = lab
    assert export_sizes(con, root) == {"week.csv": 1_989_452, "week.parquet": 831_038, "week_agg.parquet": 1_149}


def test_idle_compute_simulation():
    starts = query_starts()
    assert len(starts) == 374
    assert {w: billed_minutes(starts, suspend_after=w) for w in (None, 240, 60, 10, 1)} == {
        None: 43_200, 240: 19_597, 60: 15_399, 10: 4_135, 1: 1_098}


def test_billed_minutes_edge_cases():
    # 1 回だけ: 実行 2 分 + 待ち 10 分。重なるクエリは延びた分だけ足す
    assert billed_minutes([0], suspend_after=10) == 12
    assert billed_minutes([0, 5], suspend_after=10) == 17
    assert billed_minutes([0, 100], suspend_after=10) == 24


def test_monthly_cost_shares_add_up():
    c = monthly_cost(Rates(), storage_gb=1000, scan_tb=10, egress_gb=100, requests=1_000_000, compute_hours=100)
    assert round(c["total"], 2) == 279.4 and round(sum(c["share"].values())) == 100


def test_scan_grows_linearly_with_rows_for_flat_but_not_for_sorted():
    checked = scale_check()
    flat = [checked[n][0] for n in sorted(checked)]
    srt = [checked[n][1] for n in sorted(checked)]
    assert near(flat[0], 0.93, 0.1) and near(flat[2], 14.41, 0.1)
    assert 3.7 < flat[1] / flat[0] < 4.3 and 14 < flat[2] / flat[0] < 17
    # 日付順は行グループ (5 万行) の粒度に支配され、行数に比例しない: 4 倍の行数で 3.9 倍(0.18→0.71 MB)、中間は 1.5 倍
    assert near(srt[0], 0.18, 0.1) and near(srt[1], 0.28, 0.1) and near(srt[2], 0.71, 0.1)


def test_case_study_before_after(tmp_path):
    r = before_after(tmp_path)
    b, a = r["before"], r["after"]
    assert (b["files"], b["stored"]) == (1, 77_619_672) and (a["files"], a["stored"]) == (3, 78_041_890)
    assert [t for t, _, _ in b["ranking"]] == ["analyst_star", "dashboard", "weekly_report"]
    assert near(b["ranking"][0][1], 388.03, 0.1) and near(b["ranking"][1][1], 370.86, 0.1) and near(a["ranking"][0][1], 24.82, 0.1)
    assert abs(b["cost"]["parts"]["scan"] - 114.82) < 5 and abs(a["cost"]["parts"]["scan"] - 7.86) < 0.4
    assert a["cost"]["parts"]["storage"] > b["cost"]["parts"]["storage"]  # 保存は増える
    assert a["cost"]["total"] < b["cost"]["total"] / 5


def test_pre_aggregation(lab):
    con, root = lab
    agg = build_daily_agg(con, root)
    assert con.execute(f"SELECT count(*) FROM read_parquet('{agg}')").fetchone()[0] == 1460
    raw, small = dashboard_bytes(con, f"read_parquet('{root}/flat.parquet')", agg)
    assert near(raw, 3.71, 0.1) and small < 50_000


def test_limit_reads_about_four_row_groups(lab):
    con, root = lab
    report = limit_report(con, root)
    assert [v[0] for v in report.values()] == [9, 49, 163]
    assert near(report[122880][1], 38.18) and near(report[20000][1], 6.70) and near(report[5000][1], 2.25)
    assert all(3.8 < v[2] < 4.8 for v in report.values())  # どの大きさでも、約 4 行グループ分


def test_footer_is_small_so_the_extra_read_is_not_the_footer(lab):
    _, root = lab
    mean_footer, n = footer_report(parquet_files(root / "daily"))
    assert n == 365 and 900 < mean_footer < 1100


def test_row_group_size_explains_the_amount_column(lab):
    con, root = lab
    small, default = row_group_effect(con, root)
    assert near(small, 2.72) and near(default, 2.18)


def test_dry_run_estimate_is_a_lower_bound_and_the_guard_refuses(lab):
    con, root = lab
    for name, est_mb in (("flat.parquet", 3.32), ("sorted.parquet", 0.14)):
        est, _ = estimate_scan(parquet_files(root / name), ["amount", "event_date"], "2026-03-01", "2026-03-07")
        actual = measure(con, f"SELECT sum(amount) FROM read_parquet('{root / name}') WHERE event_date "
                              "BETWEEN '2026-03-01' AND '2026-03-07'")["read_bytes"]
        assert near(est, est_mb) and est <= actual  # 見積りは実測以下 (読み取りの粒度のぶん低め)
    with pytest.raises(RuntimeError):
        check_budget(parquet_files(root / "flat.parquet"), ["amount", "event_date"], "2026-03-01", "2026-03-07", 1_000_000)
    assert check_budget(parquet_files(root / "sorted.parquet"), ["amount", "event_date"], "2026-03-01", "2026-03-07", 1_000_000) > 0


def test_second_filter_column_is_not_helped_by_sorting(lab):
    con, root = lab
    r = two_column_report(con, root)
    assert near(r[("日付順", "日付で絞る")], 0.28) and near(r[("日付順", "顧客番号で絞る")], 7.32)
    assert near(r[("顧客番号順", "日付で絞る")], 4.27) and near(r[("顧客番号順", "顧客番号で絞る")], 0.29)


def test_codec_time_ordering(lab):
    con, root = lab
    r = codec_report(con, root)
    assert r["zstd"]["write_s"] > r["uncompressed"]["write_s"]


def test_request_cost_and_sensitivity_table(tmp_path):
    result = before_after(tmp_path)
    req = request_cost(tmp_path)
    assert (req["daily"], req["compacted"]) == (386, 6)
    assert round(req["monthly"]["daily"], 4) == 0.4632 and round(req["monthly"]["compacted"], 4) == 0.0072
    rows = sensitivity_rows(result)
    table = Path(__file__).parents[2] / "data" / "tables" / "a10-price-sensitivity.csv"
    with open(table, encoding="utf-8", newline="") as f:
        expected = list(csv.reader(f))[1:]
    # 表は、コードが出した値。読んだバイト数の揺れで丸めの末尾が 0.01 動くことがあるので、金額は 0.05 の幅で比べる
    assert len(rows) == len(expected)
    for got, want in zip(rows, expected):
        assert got[:2] == want[:2] and got[4] == want[4]
        assert all(abs(float(g) - float(w)) < 0.05 for g, w in zip(got[2:4], want[2:4]))
    assert all(r[4] == "変更後が安い" for r in rows)


def test_mb_format():
    assert mb(3_392_645) == "3.39 MB"
