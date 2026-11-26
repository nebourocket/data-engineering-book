"""第4章のコードの検査。模型の数字は決まった値になるので、表と本文の数字をそのまま確かめます。"""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import kafka_flow  # noqa: E402
import make_table  # noqa: E402
import schema_change  # noqa: E402
import stream_sim as sim  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def test_events_are_deterministic_and_sorted_by_arrival():
    a, b = sim.make_events("mixed"), sim.make_events("mixed")
    assert a == b and len(a) == 6000
    assert [e.arrival for e in a] == sorted(e.arrival for e in a)
    assert any(x.event_time > y.event_time for x, y in zip(a, a[1:]))  # 届いた順では時刻が前後する


def test_window_assignment():
    assert sim.tumbling_start(125, 60) == 120
    assert sim.sliding_starts(125, 60, 20) == [80, 100, 120]
    assert sim.sessionize([0, 10, 50, 400, 410], 60) == [(0, 50, 3), (400, 410, 2)]


def test_late_event_is_dropped_after_window_closes():
    agg = sim.WindowAggregator(size=60, lateness=10)
    agg.process(sim.Event(1, "寝具", 5, 5))
    closed = agg.process(sim.Event(2, "寝具", 75, 75))  # watermark = 65 >= 60: 最初の窓が確定
    assert closed == [(0, "寝具", 1, 75)]
    assert agg.process(sim.Event(3, "寝具", 30, 80)) == [] and agg.dropped == 1


def test_longer_watermark_drops_less_but_waits_and_holds_more():
    events = sim.make_events("mixed")
    short, long_ = sim.evaluate(events, 10), sim.evaluate(events, 300)
    assert long_["dropped_pct"] < short["dropped_pct"]
    assert long_["delay_mean"] > short["delay_mean"]
    assert long_["peak_state"] > short["peak_state"]


def test_table_csv_matches_code():
    path = ROOT / "data" / "tables" / "a04-watermark-tradeoff.csv"
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    expected = [[str(x) for x in r] for r in make_table.tradeoff_rows()]
    assert rows[0] == make_table.HEADER and rows[1:] == expected


def test_crash_recovery_duplicates_unless_idempotent():
    events = sim.make_events("mixed")
    clean = sim.run_with_crash(events, 60, 10**9, 1000, idempotent=True)
    appended = sim.run_with_crash(events, 60, 2999, 1000, idempotent=False)
    upserted = sim.run_with_crash(events, 60, 2999, 1000, idempotent=True)
    assert len(appended) > len(set(appended))
    assert upserted == clean


def test_backlog_arithmetic():
    assert sim.backlog_after(120, 100, 600) == 12000
    assert sim.seconds_to_drain(12000, 80, 100) == 600
    assert sim.seconds_to_drain(12000, 100, 100) is None


def test_kafka_roundtrip_lag_and_transactions(kafka_bootstrap):
    events = sim.make_events("mixed", n=300)
    topic = kafka_flow.new_topic(kafka_bootstrap)
    tx_topic = kafka_flow.new_topic(kafka_bootstrap)
    try:
        kafka_flow.produce_events(kafka_bootstrap, topic, events)
        assert kafka_flow.read_events(kafka_bootstrap, topic, 300, "g-read") == events
        assert kafka_flow.consumer_lag(kafka_bootstrap, topic, "g-lag", 120) == (300, 120, 180)
        assert kafka_flow.transaction_demo(kafka_bootstrap, tx_topic) == {"read_uncommitted": 5, "read_committed": 3}
    finally:
        kafka_flow.delete_topic(kafka_bootstrap, topic)
        kafka_flow.delete_topic(kafka_bootstrap, tx_topic)


def test_delay_stats_and_walkthrough():
    stats = {m: sim.delay_stats(sim.make_events(m)) for m in sim.MODELS}
    assert (stats["fast"]["p99"] < stats["long_tail"]["p99"] < stats["mixed"]["p99"]
            < stats["mobile"]["p99"])
    assert stats["mobile"]["max"] >= 300
    steps = sim.walkthrough()
    assert [s["action"] for s in steps] == ["数えた", "数えた", "数えた", "数えた", "捨てた", "数えた"]
    assert steps[3]["closed"] == [(0, 2)] and steps[5]["closed"] == [(60, 2)]


def test_update_mode_emits_more_rows_than_append():
    events = sim.make_events("mixed")
    assert sim.update_rows(events, 60) > len(sim.truth(events)) * 0.9


def test_schema_change_strict_reader_fails_tolerant_does_not():
    messages = schema_change.make_messages()
    assert schema_change.count_failures(messages, schema_change.read_strict) == 300
    assert schema_change.count_failures(messages, schema_change.read_tolerant) == 0


def test_state_grows_with_keys_until_events_run_out():
    events = sim.make_events("mixed")
    small, mid, big = (sim.peak_state_with_keys(events, 600, k) for k in (5, 500, 5000))
    assert small < mid and mid == big  # キーが増えても、開いている窓の中の行数が上限になる
    assert big < len(events) / 3


def test_chapter_numbers_are_exact():
    events = sim.make_events("mixed")
    assert [sim.update_rows(events, w) for w in (10, 60, 300)] == [1891, 2048, 2254]
    assert [sim.evaluate(events, w)["output_rows"] for w in (10, 60, 300)] == [300, 300, 300]
    assert [sim.peak_state_with_keys(events, w, 500) for w in (60, 600)] == [229, 1203]
    big = sim.make_events("mixed", n=60000)
    assert [sim.peak_state_with_keys(big, w, 5000) for w in (60, 600)] == [1999, 10953]
    assert [sim.peak_state_with_keys(big, w, 500) for w in (60, 600)] == [1000, 5500]
    stats = {m: sim.delay_stats(sim.make_events(m)) for m in sim.MODELS}
    assert [(stats[m]["p50"], stats[m]["p99"], stats[m]["max"]) for m in sim.MODELS] == [
        (1, 8, 20), (2, 218, 463), (7, 135, 1003), (2, 781, 896)]
    assert [round(stats[m]["out_of_order_pct"], 1) for m in sim.MODELS] == [20.0, 27.8, 33.7, 26.9]


def test_crash_with_real_sqlite_sink():
    events = sim.make_events("mixed")
    clean = sim.run_with_crash(events, 60, 10**9, 1000, idempotent=True)
    assert len(clean) == 300
    assert len(sim.run_with_crash(events, 60, 2999, 1000, idempotent=False)) == 350
    sweep = sim.crash_sweep(events)
    assert sweep["plain_extra_rows"] == [20, 0, 25, 0, 25, 0, 25, 0, 25, 0, 30]
    assert sweep["plain_with_duplicates"] == 6 and sweep["idempotent_same"] == 11


def test_three_tiers_magnitude():
    t = sim.three_tiers(sim.make_events("mixed"))
    assert round(100 * t["dashboard"]["rel_err_median"], 1) == 4.5 and round(100 * t["dashboard"]["rel_err_p95"]) == 15
    assert round(t["dashboard"]["missing_total_pct"], 2) == 4.87
    assert t["confirmed"]["rel_err_p95"] == 0 and round(t["confirmed"]["missing_total_pct"], 2) == 0.17
    assert t["nightly"] == {"rel_err_median": 0, "rel_err_p95": 0, "missing_total_pct": 0}


def test_real_spark_differs_from_the_model():
    pytest.importorskip("pyspark")
    import spark_walk
    log = dict(spark_walk.run())
    assert log[4] == [(0, 3)] and log[6] == [(60, 2)]  # 遅れた 50 も数えられ、窓は 1 バッチ遅れで出る
    assert all(log[i] == [] for i in (0, 1, 2, 3, 5))
