"""第9章のコードの検査。PostgreSQL が要るものは PG_ADMIN_DSN (ロールを作れる接続) が無ければ skip します。"""
import os

import pytest

from govlab_access import (SETUP, access_matrix, attempt, audit_demo, grant_regressions, read_bypass,
                           rls_exceptions, row_level, who_touched)
from govlab_case import run
from govlab_data import load_shop
from govlab_erasure import build, erase, files_per_customer, touched
from govlab_lineage import pii_tables, pii_trail, unreviewed
from govlab_pg import sandbox
from lineage_events import one_night
import duckdb

from govlab_pseudo import dictionary_attack, keyed_hash, mask_email, plain_hash, small_groups


@pytest.fixture
def box():
    dsn = os.environ.get("PG_ADMIN_DSN")
    if not dsn:
        if os.environ.get("DE_BOOK_REQUIRE_SERVICES") == "1":
            pytest.fail("環境変数 PG_ADMIN_DSN が未設定です")
        pytest.skip("環境変数 PG_ADMIN_DSN が未設定です")
    with sandbox(dsn, SETUP) as b:
        yield b


def test_data_shape():
    customers, orders = load_shop()
    assert len(customers) == 505 and len(orders) == 3000
    assert sum(1 for c in customers if c["email"]) == 485
    assert sum(1 for o in orders if o["note"] and "@" in o["note"]) == 55
    assert sum(1 for o in orders if "090-" in o["note"]) == 81


def test_access_matrix(box):
    got = {(role, sql): (status, result) for role, sql, status, result in access_matrix(box)}
    assert got[("a09_analyst", "SELECT customer_id, prefecture FROM a09.customers")] == ("ok", "505 行")
    assert got[("a09_analyst", "SELECT customer_id, email FROM a09.customers")] == ("error", "permission denied for table customers")
    assert got[("a09_analyst", "SELECT * FROM a09.customers")][0] == "error"
    assert got[("a09_analyst", "SELECT note FROM a09.orders")][0] == "error"
    masked = "SELECT email, phone FROM a09.customers_masked WHERE customer_id = 1"
    assert got[("a09_analyst", masked)] == ("ok", [("u***@example.com", "***-****-7919")])
    assert got[("a09_etl", masked)] == ("ok", [("user0001@example.com", "090-0001-7919")])


def test_row_level_security_and_view_pitfall(box):
    assert row_level(box) == {"owner": 505, "analyst": 505, "support": 95,
                              "support_leaky_view": 505, "support_invoker_view": 95}
    assert attempt(box, "a09_support", "SELECT email FROM a09.customers")[0] == "error"


def test_audit_log(box):
    a = audit_demo(box)
    assert a["summary"] == [("a09_etl", "DELETE", 1), ("a09_etl", "UPDATE", 3),
                            ("a09_support", "READ", 2), ("a09_support", "READ_DENIED", 1)]
    assert a["reads"] == [(5, "READ", "問い合わせ #1234"), (8, "READ", "問い合わせ #1235"), (1, "READ_DENIED", "好奇心")]
    assert a["tamper"] == ("error", "permission denied for table audit_log")
    with box.connect() as admin:  # 値そのものはログに入れない
        cols = [r[0] for r in admin.execute("SELECT detail FROM a09.audit_log WHERE op = 'UPDATE'").fetchall()]
    assert cols == ["phone", "phone", "phone"]


def test_support_lookup_returns_row_only_in_region(box):
    ok = attempt(box, "a09_support", "SELECT * FROM a09.lookup_customer(5, 'テスト')")
    assert ok[0] == "ok" and len(ok[1]) == 1 and ok[1][0][1].startswith("user")
    assert attempt(box, "a09_support", "SELECT * FROM a09.lookup_customer(1, 'テスト')") == ("ok", [])
    assert attempt(box, "a09_analyst", "SELECT * FROM a09.lookup_customer(5, 'テスト')")[0] == "error"


def test_masking_functions():
    assert mask_email("user0001@example.com") == "u***@example.com" and mask_email(None) is None
    assert mask_email("ab@x.jp") == "a***@x.jp"
    assert keyed_hash("a", b"k1") != keyed_hash("a", b"k2") and len(keyed_hash("a", b"k")) == 16
    # 鍵が違えば同じ入力でも一致しない = 鍵を知らない攻撃者は候補を突き合わせられない
    assert dictionary_attack([keyed_hash("user0007@example.com", b"k1")], plain_hash) == 0


def test_case_study():
    r = run()
    assert r["scan_before"] == {("customers", "email", "email"): 485, ("customers", "phone", "phone"): 505,
                                ("orders", "note", "email"): 55, ("orders", "note", "phone"): 81}
    assert r["scan_after"] == {}
    assert r["emails"] == 485 and r["naive_recovered"] == 485
    assert r["hmac_recovered"] == 0 and r["insider_with_key"] == 485
    assert r["k_pref_year"] == (505, 350) and r["k_raw"] == (505, 505)
    assert r["k_dev_month"] == (137, 102) and r["k_dev"] == (10, 36)
    assert r["dev_key_shared"] == r["orders"] == 3000


def test_dictionary_attack_needs_guessable_format():
    assert dictionary_attack([plain_hash("user0007@example.com"), plain_hash("someone@else.example")], plain_hash) == 1


def test_small_groups_counts_people_in_groups_below_k():
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('a', 1), ('a', 1), ('a', 1), ('b', 2), ('c', 3)) v(x, y)")
    assert small_groups(con, "t", ["x", "y"], k=2) == (2, 3)  # b と c の 1 人ずつ
    assert small_groups(con, "t", ["x"], k=2) == (2, 3)
    assert small_groups(con, "t", ["x"], k=4) == (5, 3)  # 全員が 4 人未満のグループ
    assert small_groups(con, "t", ["x"], k=1) == (0, 3)


def test_erasure_cost_depends_on_layout(tmp_path):
    con, root = build(tmp_path)
    assert touched(con, root / "by_month", 42) == (2, 6, 31_348, 59_785)
    assert touched(con, root / "by_customer", 42) == (1, 16, 4_530, 74_200)
    assert files_per_customer(con) == (2.83, 4)
    assert erase(con, root / "by_month", 42) == 2 and erase(con, root / "by_customer", 42) == 1
    assert touched(con, root / "by_month", 42)[0] == 0 and touched(con, root / "by_customer", 42)[0] == 0
    left = con.execute(f"SELECT count(*) FROM read_parquet('{root}/by_month/*/*.parquet', hive_partitioning=false)").fetchone()[0]
    total = con.execute("SELECT count(*) FROM o WHERE customer_id <> 42").fetchone()[0]
    assert left == total


def test_rls_is_really_enabled_and_exceptions(box):
    with box.connect() as admin:
        assert admin.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'a09.customers'::regclass").fetchone()[0]
    assert rls_exceptions(box) == {"owner_with_force": 0, "superuser": 505, "bypassrls_role": 505}
    with box.connect() as admin:  # 後片付けで FORCE を戻している
        assert not admin.execute("SELECT relforcerowsecurity FROM pg_class WHERE oid = 'a09.customers'::regclass").fetchone()[0]


def test_reading_the_table_directly_leaves_no_read_record(box):
    audit_demo(box)
    assert read_bypass(box) == (1, 1)
    assert who_touched(box, 8) == [("a09_support", "READ", "問い合わせ #1235")]
    assert [row[1] for row in who_touched(box, 500)] == ["DELETE"]


def test_grant_regression_check_detects_a_bad_grant(box):
    assert grant_regressions(box) == []
    with box.connect() as admin:
        admin.execute("GRANT SELECT (email) ON a09.customers TO a09_analyst")
    assert grant_regressions(box) == [("a09_analyst", "SELECT email FROM a09.customers", False)]


def test_pii_trail_follows_lineage_downstream():
    hits = run()["scan_before"]
    assert pii_tables(hits) == ["raw.orders"]
    trail = pii_trail(one_night(), pii_tables(hits))
    assert trail == {"raw.orders": ["mart.fact_sales", "ml.churn_features", "mart.daily_revenue"]}
    assert unreviewed(trail, ["raw.orders", "mart.fact_sales"]) == ["mart.daily_revenue", "ml.churn_features"]
    assert unreviewed(trail, ["mart.fact_sales", "ml.churn_features", "mart.daily_revenue"]) == []
