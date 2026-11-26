"""第5章のコードの検査。サービスが要るものは PG_DSN / PG_LOGICAL_DSN が無ければ skip します。"""
import json
from pathlib import Path

import duckdb
import pytest

import cdc_case_study
import consumers
import debezium_config
import dwh_apply
import logical
import logical_demo
import outbox
import query_cdc
from sandbox import sandbox

HERE = Path(__file__).parent


def test_query_based_cdc_misses_delete_stale_update_and_intermediate_state(pg_dsn):
    with sandbox(pg_dsn) as box:
        r = query_cdc.run_scenario(box)
    assert r["initial_rows"] == 200
    assert r["seen_after_changes"] == [(1, "delivered"), (4, "shipped")]  # 注文 1 の途中の shipped は見えない
    assert r["seen_after_slow_commit"] == []  # 注文 3 は永久に見えない
    assert r["wrong_rows"] == [2, 3]  # 2: 消えたのに残る / 3: 古いまま


def test_dual_write_loses_or_invents_events_but_outbox_does_not(pg_dsn):
    with sandbox(pg_dsn) as box:
        r = outbox.compare(box)
    assert r["failures_injected"] == 58
    assert r["dual_write_commit_first"] == {"orders": 1000, "messages": 942, "lost_events": 58}
    assert r["dual_write_publish_first"] == {"orders": 942, "messages": 1000, "phantom_events": 58}
    assert r["outbox"] == {"orders": 942, "messages": 1442, "distinct_events": 942,
                           "lost_events": 0, "duplicates": 500}


def test_consumers_survive_reordering_and_duplicates(pg_dsn):
    with sandbox(pg_dsn) as box:
        states = consumers.run_state_consumers(box)
        points = consumers.run_points_consumers(box)
    assert states["events"] == 2000 and states["delivered"] == 2211
    assert states["last_write_wins"]["wrong_orders"] == 378
    assert states["version_guard"]["wrong_orders"] == 0
    assert points["true_total"] == 911 and points["blind"] == 1012 and points["inbox"] == 911


def test_event_styles_and_event_sourcing():
    r = consumers.notification_vs_state([(7, "paid"), (7, "shipped"), (7, "delivered")])
    assert r["notice_seen"] == ["delivered"] * 3 and r["carried_seen"] == ["paid", "shipped", "delivered"]
    assert r["lookups_needed"] == 3 and r["bytes_notice"] < r["bytes_carried"]
    events = [{"type": "OrderPlaced", "order_id": 1, "amount": 900},
              {"type": "OrderShipped", "order_id": 1}, {"type": "OrderCancelled", "order_id": 1}]
    assert consumers.fold(events) == {1: {"status": "cancelled", "amount": 900}}
    assert consumers.fold(events[:2])[1]["status"] == "shipped"


def test_dwh_soft_delete_is_stable_under_replay_and_reordering():
    base = dwh_apply.run_dwh()
    assert base["log_rows"] == 2548 and base["deleted_in_source"] == 46
    assert base["soft_live"] == base["scd2_current"] == base["hard_rows"] == 954
    replay = dwh_apply.run_dwh(replay_first=True)
    assert replay["hard_rows"] == 964 and replay["soft_live"] == 954  # ハード削除は消した行が生き返る
    shuffled = dwh_apply.run_dwh(shuffle_seed=1)
    assert shuffled["hard_rows"] == 995 and shuffled["soft_live"] == 954
    assert base["scd2_rows"] == 2502 == base["log_rows"] - base["deleted_in_source"]


def test_scd2_closes_the_row_on_delete():
    con = duckdb.connect()
    dwh_apply.load_log(con, dwh_apply.make_changelog())
    con.execute(dwh_apply.SCD2)
    gone = con.execute("SELECT order_id FROM cdc_log WHERE op = 'd' ORDER BY lsn LIMIT 1").fetchone()[0]
    last = con.execute("SELECT is_current, valid_to IS NOT NULL FROM orders_scd2 WHERE order_id = ? "
                       "ORDER BY valid_from DESC LIMIT 1", [gone]).fetchone()
    assert last == (False, True)


def test_connector_json_is_well_formed():
    doc = debezium_config.load(HERE / "connector.json")
    assert debezium_config.check_connector(doc) == []
    bad = json.loads(json.dumps(doc))
    cfg = bad["config"]
    cfg["database.password"] = "secret"
    cfg["slot.name"] = "Debezium-Orders"
    cfg["plugin.name"] = "decoderbufs"
    cfg["table.include.list"] = "orders"
    cfg["heartbeat.interval.ms"] = "0"
    del cfg["publication.name"]
    assert len(debezium_config.check_connector(bad)) == 6


# --- wal_level=logical が要るもの ---

def test_wal_sees_what_the_query_based_poller_misses(logical_dsn):
    lines, changes = logical_demo.wal_sees_everything(logical_dsn)
    assert len(changes) == 5  # 更新 4 回 + 削除 1 回 (注文 1 の途中の更新も含む)
    assert sum("DELETE" in c for c in changes) == 1
    assert "status[text]:'shipped'" in " ".join(changes)  # 途中の状態も見える
    assert changes[-1].find("order_id[integer]:3") > 0  # 遅れてコミットした注文 3 は、コミット順の最後に出る


def test_pgoutput_default_identity_has_no_before_image(logical_dsn):
    kinds, changes, envelopes, keys = logical_demo.pgoutput_events(logical_dsn, False)
    assert kinds == list("BRICBUCBUCBDC")
    assert changes[1]["old"] is None  # 既定の REPLICA IDENTITY: 主キーが変わらない更新に before は無い
    assert changes[2]["old_kind"] == "K" and changes[3]["old_kind"] == "K"
    assert [e["op"] for e in envelopes] == ["c", "u", "u", "d"]
    assert envelopes[3]["after"] is None


def test_pgoutput_replica_identity_full_has_before_image(logical_dsn):
    _, changes, envelopes, keys = logical_demo.pgoutput_events(logical_dsn, True)
    assert envelopes[1]["before"] == {"order_id": 1, "status": "placed", "amount": 1200}
    assert envelopes[1]["after"]["status"] == "paid" and changes[1]["old_kind"] == "O"
    assert envelopes[3]["before"]["order_id"] == 10
    assert keys == ['{"order_id": 1}', '{"order_id": 1}', '{"order_id": 10}', '{"order_id": 10}']


def test_idle_slot_keeps_wal(logical_dsn):
    before, after = logical_demo.slot_keeps_wal(logical_dsn)
    assert before["retained_bytes"] < 1_000_000
    assert after["retained_bytes"] > 4_000_000  # 20,000 行 x 約 200 バイトの WAL が捨てられない


def test_slot_becomes_lost_when_limit_is_exceeded(logical_dsn):
    status, error = logical_demo.slot_gets_lost(logical_dsn)
    assert status["wal_status"] == "lost"
    assert "can no longer get changes" in error


def test_decoder_ignores_unknown_messages():
    assert logical.PgoutputDecoder().decode(b"Y\x00\x00\x00\x01") is None


def test_case_study_wal_matches_truth_and_polling_does_not(logical_dsn):
    r = cdc_case_study.run(logical_dsn)
    assert r["rows_read"] == {"full_reload": 20000, "updated_at": 600, "wal": 650}
    assert r["wrong_rows_after"] == {"full_reload_first": 10, "full_reload_next_run": 0,
                                     "updated_at": 50, "wal": 0}  # 削除 40 + 遅れた更新 10
    assert 100 < r["wal_bytes_per_change"] < 1000


def test_replica_identity_full_costs_more_wal_per_update(logical_dsn):
    default = cdc_case_study.wal_per_update(logical_dsn, "DEFAULT")
    full = cdc_case_study.wal_per_update(logical_dsn, "FULL")
    assert full["wal_bytes_per_update"] > default["wal_bytes_per_update"]
    assert abs(default["idle_slot_holds_per_update"] - default["wal_bytes_per_update"]) < 20  # 放置したスロットは WAL を捨てさせない


def test_envelope_carries_real_lsn_and_commit_time(logical_dsn):
    _, _, envelopes, _ = logical_demo.pgoutput_events(logical_dsn, True)
    assert all(e["source"]["lsn"] > 0 for e in envelopes)
    assert all(e["ts_ms"] > 1_700_000_000_000 for e in envelopes)  # 2023 年以降のミリ秒


def test_parallel_relays_do_not_duplicate_or_lose(pg_dsn):
    with sandbox(pg_dsn) as box:
        r = outbox.relay_in_parallel(box)
    assert r == {"messages": 400, "distinct": 400, "per_worker_sum": 400}
