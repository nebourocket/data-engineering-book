"""第8章のコードの検査。件数・検知・影響範囲を確かめます (秒数は見ません)。"""
import contract_check
import freshness_volume as fv
import lineage_events
import obs_case
import slo_burn


def test_freshness_finds_the_two_late_days():
    con = fv.load_into_duckdb(fv.make_load_log())
    days = [str(d) for d, _ in con.execute(fv.FRESHNESS_SQL).fetchall()]
    assert days == ["2026-02-10", "2026-04-11"]


def test_naive_k_trades_false_alarms_for_misses_and_weekday_baseline_needs_no_k():
    rows = [r["row_count"] for r in fv.make_load_log()]
    good = fv.score(fv.weekday_flags(rows), 28)
    assert good == {"detected": [55, 70, 85], "missed": [], "false_alarms": 0}
    assert fv.score(fv.naive_flags(rows, k=3), 28)["missed"] == [70]
    assert fv.score(fv.naive_flags(rows, k=1.5), 28)["false_alarms"] == 12
    k2 = fv.score(fv.naive_flags(rows, k=2), 28)
    assert (k2["missed"], k2["false_alarms"]) == ([], 1)
    # floor (中央値の 2 割) が誤報を抑えている。0 にすると誤報が出る
    assert fv.score(fv.weekday_flags(rows, floor=0), 28) == {"detected": [55, 70, 85], "missed": [], "false_alarms": 18}


def test_seeds_one_to_seven_differ_little():
    got = []
    for seed in range(1, 8):
        rows = [r["row_count"] for r in fv.make_load_log(seed)]
        a, b = fv.score(fv.naive_flags(rows, k=2), 28), fv.score(fv.weekday_flags(rows), 28)
        got.append((len(a["missed"]), a["false_alarms"], len(b["missed"]), b["false_alarms"]))
    assert got == [(0, 1, 0, 0), (0, 1, 0, 0), (0, 1, 0, 1), (0, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 0), (0, 1, 0, 0)]


def test_backfill_and_late_data_raise_alarms_unless_skipped():
    rows = [r["row_count"] for r in fv.make_load_log()]
    shifted = fv.with_backfill_and_late_data(rows)
    extra = lambda flags: [i for i in flags if i not in fv.INCIDENTS]  # noqa: E731
    assert extra(fv.weekday_flags(shifted)) == [90, 95, 96]
    assert extra(fv.weekday_flags(shifted, skip={fv.BACKFILL_DAY})) == [95, 96]
    assert (rows[90], shifted[90]) == (2080, 12379)


def test_budget_and_burn_rate():
    bad = slo_burn.bad_flags(slo_burn.build_lag(slo_burn.BIG))
    assert sum(bad) == 80 and round(slo_burn.budget_used(bad), 3) == 0.185
    flap = slo_burn.bad_flags(slo_burn.build_lag(slo_burn.FLAPPING))
    assert sum(flap) == 42 and round(slo_burn.budget_used(flap), 3) == 0.097
    assert [obs_case.bad_samples(s) for s in slo_burn.BIG] == [(55, 335), (25, 185)]
    assert {obs_case.bad_samples(s) for s in slo_burn.FLAPPING} == {(7, 95)}
    assert slo_burn.LIMIT == 60  # 契約の書類 (freshness_minutes) から読んでいる
    assert round(slo_burn.WINDOWS["3d"] * (1 - slo_burn.SLO), 1) == 43.2  # 25 < 43.2 < 55 なので、チケットは 300 分の停止だけ
    rates = slo_burn.burn_rates([1] * 12 + [0] * 12, 12)
    assert rates[11] == 1 / (1 - slo_burn.SLO) and rates[23] == 0.0 and rates[5] == 0.0


def test_burn_rate_alerts_are_quiet_for_short_stalls_but_not_for_long_ones():
    flap = obs_case.run_alerts(slo_burn.FLAPPING)
    assert flap["naive"][0] == 6 and flap["page_fast"][0] == flap["page_slow"][0] == flap["ticket"][0] == 0
    big = obs_case.run_alerts(slo_burn.BIG)
    assert big["page_fast"] == (2, [65, 65]) and big["naive"] == (2, [25, 25])
    assert big["page_slow"] == (2, [130, 130]) and big["ticket"] == (1, [240, None])
    assert flap["naive"][1] == [25] * 6


def test_lineage_impact_and_failed_runs():
    events = lineage_events.one_night()
    assert len(events) == 12 and {e["eventType"] for e in events} == {"START", "COMPLETE"}
    assert len({e["run"]["runId"] for e in events}) == 6  # START と COMPLETE は同じ runId
    graph = lineage_events.build_graph(events)
    assert lineage_events.downstream(graph, "raw.orders") == ["mart.fact_sales", "ml.churn_features", "mart.daily_revenue"]
    assert lineage_events.downstream(graph, "raw.events") == ["ml.churn_features"]
    assert lineage_events.downstream(graph, "raw.order_items") == ["mart.fact_sales", "mart.daily_revenue"]
    failed = lineage_events.one_night(failed_jobs=("build_fact_sales",))
    # 失敗した実行も構造には残るので、下流は消えない。古いままの表として別に出る
    assert lineage_events.downstream(lineage_events.build_graph(failed), "raw.orders") == lineage_events.downstream(graph, "raw.orders")
    assert lineage_events.stale_tables(failed) == (["mart.fact_sales"], ["mart.daily_revenue"])
    assert lineage_events.stale_tables(events) == ([], [])


def test_schema_facet_catches_rename_against_contract():
    v1 = contract_check.load_schema("orders.v1.json")
    renamed = [(n, t) if n != "total_amount" else ("amount", t) for n, t in lineage_events.ORDERS_FIELDS]
    assert lineage_events.schema_drift(lineage_events.one_night(), "raw.orders", v1) == ([], [])
    assert lineage_events.schema_drift(lineage_events.one_night(orders_fields=renamed), "raw.orders", v1) == (["amount"], ["total_amount"])


def test_monitor_cost_rows():
    assert [obs_case.daily_count_seconds(s, repeat=1)[:2] for s in (1, 100)] == [(3000, 172), (300000, 172)]


def test_freshness_plus_volume_find_all_five_incidents():
    log = fv.make_load_log()
    rows = [r["row_count"] for r in log]
    late = {(r["d"] - fv.START).days for r in log if r["finished_at"] > __import__("datetime").datetime(r["d"].year, r["d"].month, r["d"].day, fv.DEADLINE_HOUR)}
    volume = set(fv.weekday_flags(rows)) - set(range(28))
    assert late == {40, 100} and volume == {55, 70, 85}
    assert late | volume == set(fv.INCIDENTS)


def test_failed_ingest_marks_everything_behind_it_stale():
    failed = lineage_events.one_night(failed_jobs=("ingest_orders",))
    assert lineage_events.stale_tables(failed) == (["raw.orders"], ["mart.daily_revenue", "mart.fact_sales", "ml.churn_features"])
