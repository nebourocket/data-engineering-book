from datetime import date
from pathlib import Path

import duckdb
import pytest

import fact_types
import scd
import star_schema


def make():
    con = duckdb.connect()
    star_schema.build_star(con)
    return con


def test_star_matches_source():
    con = make()
    star = con.execute(f"SELECT sum(sales) FROM ({star_schema.STAR_QUERY})").fetchone()[0]
    source = con.execute(
        "SELECT sum(i.quantity * i.unit_price) FROM order_items AS i JOIN orders AS o USING (order_id)"
        " WHERE lower(o.status) <> 'cancelled'").fetchone()[0]
    assert star == source == 34321900
    # 粒度: 注文明細 1 行 = ファクト 1 行、(order_id, line_no) は重複しない
    assert con.execute("SELECT count(*), count(DISTINCT (order_id, line_no)) FROM fact_order_items").fetchone() \
        == (7469, 7469)
    assert con.execute("SELECT count(*) FROM order_items").fetchone() == (7469,)
    # 表記ゆれ SHIPPED は dim_order_status で 1 つにそろう
    assert [r[0] for r in con.execute("SELECT status FROM dim_order_status ORDER BY 1").fetchall()] \
        == ["cancelled", "delivered", "placed", "shipped"]
    assert con.execute("SELECT count(*) FROM fact_order_items WHERE customer_key = -1").fetchone() == (0,)


def test_date_dimension():
    con = make()
    assert con.execute("SELECT count(*) FROM dim_date WHERE year = 2026").fetchone() == (365,)
    assert con.execute("SELECT date_key, is_weekend FROM dim_date WHERE date = DATE '2026-01-03'").fetchone() \
        == (20260103, True)


def test_scd1_overwrites_history():
    con = make()
    con.execute(scd.SCD1_SQL)
    assert con.execute("SELECT name FROM dim_product WHERE product_id = 1").fetchone() == ("枕(標準・改良版)",)
    assert con.execute("SELECT count(*) FROM dim_product WHERE product_id = 1").fetchone() == (1,)


def test_scd2_history_and_as_of_join():
    con = duckdb.connect()
    out = scd.run_scd2_demo(con, date(2026, 4, 1))
    assert out["changed"] == 3 and out["changed_again"] == 0  # 再実行しても増えない
    assert out["movers"] == [1, 6, 7]
    assert out["history"] == [
        (1, "愛知", date(2026, 3, 20), date(2026, 4, 1), False),
        (1, "沖縄", date(2026, 4, 1), date(9999, 12, 31), True)]
    # 版の区間が重ならず、現行は顧客ごとに 1 行
    assert con.execute("SELECT count(*) FROM dim_customer AS a JOIN dim_customer AS b"
                       " ON a.customer_id = b.customer_id AND a.customer_key < b.customer_key"
                       " AND a.valid_from < b.valid_to AND b.valid_from < a.valid_to").fetchone() == (0,)
    assert con.execute("SELECT max(n) FROM (SELECT count(*) AS n FROM dim_customer WHERE is_current"
                       " GROUP BY customer_id)").fetchone() == (1,)
    # 売上の合計は変わらず、都道府県の割り当てだけが違う
    assert sum(v for _, v in out["as_was"]) == sum(v for _, v in out["as_is"]) == 177850
    assert len(out["as_was"]) > 1 and len(out["as_is"]) == 1
    assert con.execute(f"SELECT sum(sales) FROM ({star_schema.STAR_QUERY})").fetchone()[0] == 34321900


def test_snowflake_and_obt_agree_with_star():
    con = duckdb.connect()
    fact_types.build_all(con)
    assert con.execute(fact_types.SNOWFLAKE_QUERY).fetchall() == con.execute(fact_types.STAR_CATEGORY_QUERY).fetchall()
    assert con.execute("SELECT count(*), sum(sales_amount) FILTER (WHERE is_sales) FROM obt_order_items"
                       ).fetchone() == (7469, 34321900)


def test_periodic_snapshot():
    con = duckdb.connect()
    fact_types.build_all(con)
    rows = con.execute("SELECT snapshot_date_key, count(*), sum(cumulative_sales)"
                       " FROM fact_customer_month_snapshot GROUP BY 1 ORDER BY 1").fetchall()
    assert [r[0] for r in rows] == [20260131, 20260228, 20260331, 20260430, 20260531]
    assert all(r[1] == 505 for r in rows)  # 売上が無い顧客の行も、毎月ある
    assert rows[-1][2] == 32650350 <= 34321900
    assert [r[2] for r in rows] == sorted(r[2] for r in rows)  # 累計なので減らない


def test_accumulating_snapshot_updates_one_row():
    shots = fact_types.fulfillment_demo(duckdb.connect())
    assert [len(s) for s in shots] == [1, 1, 1]
    assert shots[0] == [(1001, 20260301, 99991231, 99991231, None, None)]
    assert shots[2] == [(1001, 20260301, 20260302, 20260305, 1, 4)]


def test_conformed_dimensions_and_fan_out():
    con = duckdb.connect()
    fact_types.build_all(con)
    rows = con.execute(fact_types.DRILL_ACROSS_SQL).fetchall()
    assert sum(r[2] or 0 for r in rows) == 34321900
    assert con.execute(fact_types.TRUE_SALES_SQL).fetchone()[0] == 34321900
    assert con.execute(fact_types.FAN_OUT_SQL).fetchone()[0] > 34321900  # 直接つなぐと水増しされる
    assert con.execute("SELECT sum(events) FROM fact_events").fetchone() == (4000,)  # 重複 40 件は除かれる


def setup_scd2():
    con = duckdb.connect()
    star_schema.build_star(con)
    con.execute(scd.MAKE_CUSTOMERS_TODAY_SQL, [[1, 6, 7]])
    return con


def dim_snapshot(con):
    return con.execute("SELECT * FROM dim_customer ORDER BY customer_key").fetchall()


def test_scd2_rejects_bad_source_and_rolls_back():
    con = setup_scd2()
    before = dim_snapshot(con)
    # ソースの customer_id が重複している
    con.execute("INSERT INTO customers_today SELECT 1, name, email, '福岡' FROM customers_today WHERE customer_id = 1")
    with pytest.raises(ValueError, match="重複"):
        scd.apply_scd2(con, date(2026, 4, 1))
    # customer_id が NULL
    con.execute("DELETE FROM customers_today WHERE customer_id = 1 AND prefecture = '福岡'")
    con.execute("INSERT INTO customers_today VALUES (NULL, 'x', NULL, '東京')")
    with pytest.raises(ValueError, match="NULL"):
        scd.apply_scd2(con, date(2026, 4, 1))
    assert dim_snapshot(con) == before  # どちらも何も変わっていない


def test_scd2_failure_midway_rolls_back_and_can_retry():
    con = setup_scd2()
    before = dim_snapshot(con)
    with pytest.raises(duckdb.Error):
        scd.apply_scd2(con, "not-a-date")  # 途中で型変換に失敗する
    assert dim_snapshot(con) == before
    assert scd.apply_scd2(con, date(2026, 4, 1)) == 3  # トランザクションが残らず、そのままやり直せる
    assert scd.scd2_problems(con) == {"gaps_or_overlaps": [], "bad_current": [], "vanished": []}


def test_scd2_rejects_as_of_before_current_version():
    con = setup_scd2()
    with pytest.raises(ValueError, match="as_of"):
        scd.apply_scd2(con, date(2026, 1, 1))  # 現在の版の valid_from（登録日）より前


def test_scd2_problem_queries_detect_damage():
    con = setup_scd2()
    scd.apply_scd2(con, date(2026, 4, 1))
    # 現行の行を 2 つにする（ソースの重複を見逃したときの状態）
    con.execute("INSERT INTO dim_customer VALUES (9001, 1, 'x', NULL, '福岡', DATE '2026-05-01', DATE '9999-12-31', true)")
    problems = scd.scd2_problems(con)
    assert problems["bad_current"] == [(1, 2)]
    assert [r[0] for r in problems["gaps_or_overlaps"]] == [1]  # 沖縄の版の期間が新しい行と重なる
    # ソースから消えた顧客は、何もされず、確認クエリで見つかる
    con.execute("DELETE FROM customers_today WHERE customer_id = 2")
    assert scd.scd2_problems(con)["vanished"] == [(2,)]
    assert con.execute("SELECT is_current FROM dim_customer WHERE customer_id = 2").fetchone() == (True,)


def test_orders_by_version_and_history_table(tmp_path):
    con = duckdb.connect()
    out = scd.run_scd2_demo(con)
    assert out["orders_by_version"] == [(1, "愛知", 1), (506, "沖縄", 3)]
    path = tmp_path / "h.csv"
    scd.write_history_csv(path)
    book = Path(__file__).resolve().parents[2] / "data" / "tables" / "b08-scd2-history.csv"
    assert path.read_text(encoding="utf-8") == book.read_text(encoding="utf-8")  # 本文の表は実行結果と同じ


def test_model_checks():
    con = make()
    assert con.execute(star_schema.ORPHAN_SQL).fetchone() == (0, 0, 0, 0)
    assert con.execute(star_schema.GRAIN_SQL).fetchone() == (7469, 7469)
    assert con.execute(star_schema.UNKNOWN_SHARE_SQL).fetchone() == (0, 7469)


def test_unknown_members_in_events_role_playing_and_junk():
    con = duckdb.connect()
    fact_types.build_all(con)
    assert con.execute("SELECT sum(events) FILTER (WHERE customer_key = -1) FROM fact_events").fetchall() == [(972,)]
    fact_types.fulfillment_demo(con)
    assert con.execute(fact_types.ROLE_PLAYING_SQL).fetchall() == [
        (1001, date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 5))]
    con.execute(fact_types.JUNK_DIM_SQL)
    assert con.execute("SELECT count(*) FROM dim_order_flags").fetchone() == (6,)
