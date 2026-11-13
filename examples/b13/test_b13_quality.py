"""第 13 章: 品質チェックの実行器・確認クエリ・隔離・dbt のテストを確かめます。"""
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import quality  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run_sql = _load("run_sql_b13", HERE.parent / "b05" / "run_sql.py")
QUERIES = run_sql.split_queries((HERE / "queries.sql").read_text(encoding="utf-8"))


@pytest.fixture
def shop(tmp_path):
    path = tmp_path / "shop.duckdb"
    quality.write_duckdb(path)
    con = duckdb.connect(str(path))
    yield con
    con.close()


def passed_by_name(results):
    return {r.check.name: r.passed for r in results}


def test_each_intentional_defect_is_found(shop):
    got = passed_by_name(quality.run_checks(shop, quality.shop_checks(), "r1"))
    failed = {name for name, ok in got.items() if not ok}
    assert failed == {
        "customers.email_not_null",  # 欠陥 1
        "customers.email_unique",  # 欠陥 2
        "orders.status_accepted_values",  # 欠陥 3
        "events.event_id_unique",  # 欠陥 4
    }
    assert got["events_late_arrival"]  # 欠陥 5 は 5% の閾値の内側 (122/4040 = 3.0%)


def test_results_are_recorded_with_utc_timestamp(shop):
    quality.run_checks(shop, quality.shop_checks(), "r1")
    n, runs = shop.execute("SELECT count(*), count(DISTINCT run_id) FROM dq_results").fetchone()
    assert (n, runs) == (len(quality.shop_checks()), 1)
    run_at = shop.execute("SELECT run_at FROM dq_results LIMIT 1").fetchone()[0]
    assert run_at.utcoffset().total_seconds() == 0
    row = shop.execute("SELECT bad, total, passed FROM dq_results "
                       "WHERE check_name = 'events.event_id_unique'").fetchone()
    assert row == (40, 4040, False)


def test_gate_stops_on_error_and_notifies_warn(shop):
    notices = []
    with pytest.raises(quality.QualityError, match=r"events\.event_id_unique"):
        quality.gate(shop, quality.shop_checks(), "r1", notify=notices.append)
    assert any("customers.email_not_null" in m for m in notices)
    assert not any("events.event_id_unique" in m for m in notices)  # error は通知でなく停止
    # 止めた回の結果も残る
    assert shop.execute("SELECT count(*) FROM dq_results").fetchone()[0] == len(quality.shop_checks())


def test_quarantine_then_gate_passes(shop):
    shop.execute(QUERIES["make_events_ranked"])
    shop.execute(QUERIES["make_events_clean"])
    shop.execute(QUERIES["make_events_quarantine"])
    assert shop.execute(QUERIES["split_balance"]).fetchone() == (4040, 4000, 40)
    reasons = shop.execute("SELECT DISTINCT reason FROM events_quarantine").fetchall()
    assert reasons == [("duplicate_event_id",)]
    notices = []
    results = quality.gate(shop, quality.shop_checks("_clean"), "r2", notify=notices.append)
    assert all(r.passed for r in results if r.check.severity == "error")
    assert {m.split(":")[0] for m in notices} == {
        "[WARN] customers.email_not_null", "[WARN] customers.email_unique",
        "[WARN] orders.status_accepted_values"}


def test_threshold_decides_pass_or_fail(shop):
    loose = quality.not_null("customers", "email", max_ratio=0.05)  # 欠け 3.96%
    tight = quality.not_null("customers", "email", max_ratio=0.02)
    a, b = quality.run_checks(shop, [loose, tight], "r1")
    assert (a.passed, b.passed) == (True, False)
    assert (b.bad, b.total) == (20, 505)


def test_unmeasurable_check_is_a_failure(shop):
    (r,) = quality.run_checks(shop, [quality.not_null("no_such_table", "x")], "r1")
    assert not r.passed and "CatalogException" in r.detail


def test_empty_baseline_is_a_failure_not_a_pass(shop):
    shop.execute("CREATE TABLE empty_events AS SELECT * FROM events WHERE false")
    (r,) = quality.run_checks(shop, [quality.volume_zscore("empty_events", "event_time", "2026-06-20")], "r1")
    assert not r.passed


def test_volume_zscore_catches_missing_day_and_spike(shop):
    check = quality.volume_zscore("events", "event_time", day="2026-06-20")
    assert quality.run_checks(shop, [check], "r1")[0].passed
    shop.execute("DELETE FROM events WHERE event_time LIKE '2026-06-20%'")
    assert not quality.run_checks(shop, [check], "r2")[0].passed
    shop.execute("INSERT INTO events SELECT 9000000 + i, 1, 'view', '2026-06-20 10:00:00', "
                 "'2026-06-20 10:00:05' FROM range(200) t(i)")
    assert not quality.run_checks(shop, [check], "r3")[0].passed


def test_freshness_and_schema_drift(shop):
    fresh = quality.freshness("events", "received_at", 48, as_of="2026-07-02 00:00:00")
    stale = quality.freshness("events", "received_at", 48, as_of="2026-07-10 00:00:00")
    assert [r.passed for r in quality.run_checks(shop, [fresh, stale], "r1")] == [True, False]
    shop.execute("ALTER TABLE customers RENAME COLUMN email TO mail")
    schema = [c for c in quality.shop_checks() if c.name == "customers_schema"][0]
    (r,) = quality.run_checks(shop, [schema], "r2")
    assert not r.passed and r.bad == 2  # email が足りず、mail が余分


def test_row_count_range(shop):
    assert quality.run_checks(shop, [quality.row_count_between("events", 1, 100)], "r1")[0].passed is False


def test_main_returns_nonzero_when_error_fails(tmp_path, capsys):
    db = tmp_path / "shop.duckdb"
    assert quality.main(str(db), run_id="r1") == 1
    assert "events.event_id_unique" in capsys.readouterr().out


def test_report_queries(shop):
    def run(name):
        return shop.execute(QUERIES[name]).fetchall()

    assert run("null_ratio") == [(505, 20, 3.96)]
    assert len(run("dup_emails")) == 5
    assert run("dup_events") == [(4040, 4000, 40)]
    assert dict(run("status_values"))["SHIPPED"] == 59
    assert run("orphans") == [(0,)]
    assert run("late_events") == [(122, 4040)]
    assert [(str(d), n) for d, n, *_ in run("daily_counts_tail")][0] == ("2026-06-29", 20)
    assert [(str(d), z) for d, _, _, z in run("daily_zscore")] == [("2026-02-24", 3.02), ("2026-02-25", 4.04)]
    quality.run_checks(shop, quality.shop_checks(), "r1")
    rates = {d: (c, p) for d, c, p, _ in run("pass_rate_by_dimension")}
    assert rates["一意性"] == (3, 1) and rates["完全性"] == (2, 1)
    quality.run_checks(shop, quality.shop_checks(), "r2")
    since = {name: n for name, _, _, n in run("failing_since")}
    assert since["events.event_id_unique"] == 2


def test_dbt_tests_report_error_and_warnings(tmp_path):
    project = HERE / "dbt_demo"
    db = tmp_path / "shop.duckdb"
    quality.write_duckdb(db)
    env = {**os.environ, "SHOP_DB": str(db), "DBT_SEND_ANONYMOUS_USAGE_STATS": "False",
           "DBT_TARGET_PATH": str(tmp_path / "target"), "DBT_LOG_PATH": str(tmp_path / "logs")}
    p = subprocess.run(["dbt", "--no-use-colors", "test", "--project-dir", str(project),
                        "--profiles-dir", str(project)], env=env, capture_output=True, text=True)
    out = p.stdout
    assert p.returncode == 1  # error が 1 件 (events.event_id の重複) なので失敗扱い
    assert re.search(r"PASS=5 WARN=2 ERROR=1", out)
    assert "WARN 20 source_not_null_shop_customers_email" in out  # 閾値 10 超 40 以下は warn
    assert "FAIL 40 source_unique_shop_events_event_id" in out  # 一意性は重複した値の数 (40) を数える
    assert "WARN 1 source_accepted_values" in out  # 表記ゆれ 59 行でも「違う値」は 1 種類


def test_exercise_answers(shop):
    import exercises

    with pytest.raises(quality.QualityError):
        quality.gate(shop, [exercises.EMAIL_STRICT], "r1")
    (r,) = quality.run_checks(shop, [exercises.QUANTITY_POSITIVE], "r2")
    assert r.passed and r.total == 7469
    assert shop.execute(QUERIES["status_values_lowered"]).fetchall() == [(0,)]
    loose_late = quality.late_arrival("events", "event_time", "received_at", max_ratio=0.02)
    assert not quality.run_checks(shop, [loose_late], "r3")[0].passed


def test_info_is_recorded_but_never_notifies_or_stops(shop):
    info = quality.not_null("customers", "email", severity="info", max_ratio=0.0)
    notices = []
    results = quality.gate(shop, [info], "r1", notify=notices.append)
    assert not results[0].passed and notices == []
    assert shop.execute("SELECT severity, passed FROM dq_results").fetchall() == [("info", False)]


def test_owner_is_shown_in_the_notice_and_saved(shop):
    check = quality.not_null("customers", "email", severity="warn", max_ratio=0.0)
    check = quality.Check(check.name, check.dimension, "warn", check.sql, 0.0, owner="会員登録チーム")
    notices = []
    quality.gate(shop, [check], "r1", notify=notices.append)
    assert "会員登録チーム" in notices[0]
    assert shop.execute("SELECT owner FROM dq_results").fetchone() == ("会員登録チーム",)


def test_quarantine_ratio_check(shop):
    shop.execute(QUERIES["make_events_ranked"])
    shop.execute(QUERIES["make_events_quarantine"])
    ok, ng = quality.run_checks(shop, [quality.quarantine_ratio("events_quarantine", "events", 0.02),
                                       quality.quarantine_ratio("events_quarantine", "events", 0.005)], "r1")
    assert (ok.passed, ng.passed) == (True, False) and ok.bad == 40


def test_quote_in_accepted_values_does_not_break_sql(shop):
    (r,) = quality.run_checks(shop, [quality.accepted_values("orders", "status", ["it's"])], "r1")
    assert r.detail == "" and r.bad == 3000


def test_exercise_price_and_clock_checks(shop):
    import exercises

    a, b = quality.run_checks(shop, [exercises.PRICE_MATCHES, exercises.RECEIVED_BEFORE_EVENT], "r1")
    assert (a.bad, a.total, a.passed) == (0, 7469, True)
    assert (b.bad, b.passed) == (0, True)
    shop.execute("UPDATE order_items SET unit_price = unit_price + 1 WHERE order_id = 1 AND line_no = 1")
    assert not quality.run_checks(shop, [exercises.PRICE_MATCHES], "r2")[0].passed


def test_unmeasurable_info_check_is_notified(shop):
    broken = quality.Check("broken", "完全性", "info", "SELECT count(*), count(*) FROM no_such_table")
    notices = []
    quality.gate(shop, [broken], "r1", notify=notices.append)  # info なので止まらない
    assert len(notices) == 1 and "CatalogException" in notices[0]


def test_dedup_tie_is_broken_by_rowid(shop):
    # 重複した行は中身が全く同じ (received_at も同じ) なので、rowid が無いと順位が付けられない
    shop.execute(QUERIES["make_events_ranked"])
    dup_ids = shop.execute("SELECT event_id FROM events GROUP BY event_id HAVING count(*) > 1").fetchall()
    assert len(dup_ids) == 40
    tied = shop.execute("""SELECT count(*) FROM (SELECT event_id FROM events GROUP BY event_id
                           HAVING count(*) > 1 AND count(DISTINCT received_at) = 1)""").fetchone()[0]
    assert tied == 40  # 40 組すべてが received_at でも同順位
    assert shop.execute("SELECT count(*) = count(DISTINCT (event_id, rn)) FROM events_ranked").fetchone()[0]
    assert shop.execute("SELECT max(rn) FROM events_ranked").fetchone()[0] == 2


def test_zscore_worked_example(tmp_path):
    import zscore_example

    w = zscore_example.worked_example()
    assert (w["mean"], sum(w["squares"]), w["variance"]) == (21, 10, 2.5)
    assert round(w["sd"], 2) == 1.58 and round(w["z"], 2) == 5.69
    out = tmp_path / "t.csv"
    zscore_example.write_table(out)
    table = HERE.parents[1] / "data" / "tables" / "b13-zscore-example.csv"
    assert out.read_text(encoding="utf-8") == table.read_text(encoding="utf-8")
