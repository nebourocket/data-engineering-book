from datetime import date

import duckdb

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
