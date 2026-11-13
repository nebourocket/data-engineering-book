"""ファクトの種類（定期スナップショット・累積スナップショット）、適合ディメンション、スノーフレーク、OBT。"""
import duckdb

from star_schema import STAR_QUERY, build_star

# スノーフレーク: 商品ディメンションからカテゴリを別の表へ出す。結合がもう 1 つ増える。
SNOWFLAKE_SQL = """
CREATE OR REPLACE TABLE dim_category AS
SELECT row_number() OVER (ORDER BY category)::INTEGER AS category_key, category
FROM (SELECT DISTINCT category FROM dim_product);
CREATE OR REPLACE TABLE dim_product_sf AS
SELECT p.product_key, p.product_id, p.name, c.category_key
FROM dim_product AS p JOIN dim_category AS c USING (category)
"""
SNOWFLAKE_QUERY = """
SELECT c.category, sum(f.sales_amount) AS sales
FROM fact_order_items AS f
JOIN dim_product_sf AS p USING (product_key)
JOIN dim_category AS c USING (category_key)
JOIN dim_order_status AS s USING (status_key)
WHERE s.is_sales
GROUP BY 1
ORDER BY 1
"""
STAR_CATEGORY_QUERY = """
SELECT p.category, sum(f.sales_amount) AS sales
FROM fact_order_items AS f
JOIN dim_product AS p USING (product_key)
JOIN dim_order_status AS s USING (status_key)
WHERE s.is_sales
GROUP BY 1
ORDER BY 1
"""

# 定期スナップショット: 月末ごとに「顧客ごとの累計購入額」を 1 行ずつ残す（その月に注文が無くても行がある）。
PERIODIC_SNAPSHOT_SQL = """
CREATE OR REPLACE TABLE fact_customer_month_snapshot AS
WITH month_ends AS (
    SELECT date_key, date FROM dim_date
    WHERE date = last_day(date) AND date <= (SELECT max(d.date) FROM fact_order_items AS f
                                              JOIN dim_date AS d USING (date_key))
),
sales AS (
    SELECT c.customer_id, d.date, f.sales_amount
    FROM fact_order_items AS f
    JOIN dim_customer AS c USING (customer_key)
    JOIN dim_date AS d USING (date_key)
    JOIN dim_order_status AS s USING (status_key)
    WHERE s.is_sales
)
SELECT m.date_key AS snapshot_date_key, c.customer_id,
       COALESCE(sum(s.sales_amount), 0) AS cumulative_sales
FROM month_ends AS m
CROSS JOIN (SELECT DISTINCT customer_id FROM dim_customer WHERE customer_id > 0) AS c
LEFT JOIN sales AS s ON s.customer_id = c.customer_id AND s.date <= m.date
GROUP BY m.date_key, c.customer_id
"""

# 累積スナップショット: 注文 1 件につき 1 行。節目（出荷・配達）が起きるたびに、同じ行を更新する。
FULFILLMENT_SQL = """
CREATE OR REPLACE TABLE fact_order_fulfillment (
    order_id INTEGER, placed_date_key INTEGER,
    shipped_date_key INTEGER DEFAULT 99991231, delivered_date_key INTEGER DEFAULT 99991231,
    days_to_ship INTEGER, days_to_deliver INTEGER)
"""
MARK_SHIPPED_SQL = """
UPDATE fact_order_fulfillment AS f
SET shipped_date_key = ?,
    days_to_ship = (SELECT date_diff('day', p.date, s.date) FROM dim_date AS p, dim_date AS s
                    WHERE p.date_key = f.placed_date_key AND s.date_key = ?)
WHERE order_id = ?
"""


def fulfillment_demo(con: duckdb.DuckDBPyConnection) -> list[list[tuple]]:
    """注文 1001 が、受付 → 出荷 → 配達と進む間の、同じ 1 行の変化を返す。"""
    build_star(con)
    con.execute(FULFILLMENT_SQL)
    con.execute("INSERT INTO fact_order_fulfillment (order_id, placed_date_key) VALUES (1001, 20260301)")
    snapshots = []
    show = "SELECT * FROM fact_order_fulfillment ORDER BY order_id"
    snapshots.append(con.execute(show).fetchall())
    con.execute(MARK_SHIPPED_SQL, [20260302, 20260302, 1001])
    snapshots.append(con.execute(show).fetchall())
    con.execute("""
        UPDATE fact_order_fulfillment AS f
        SET delivered_date_key = 20260305,
            days_to_deliver = (SELECT date_diff('day', p.date, s.date) FROM dim_date AS p, dim_date AS s
                               WHERE p.date_key = f.placed_date_key AND s.date_key = 20260305)
        WHERE order_id = 1001""")
    snapshots.append(con.execute(show).fetchall())
    return snapshots


# ロールプレイングディメンション: 同じ dim_date を、受付日・出荷日・配達日の 3 つの役割で結合する。
ROLE_PLAYING_SQL = """
SELECT f.order_id, placed.date AS placed_on, shipped.date AS shipped_on, delivered.date AS delivered_on
FROM fact_order_fulfillment AS f
JOIN dim_date AS placed ON placed.date_key = f.placed_date_key
JOIN dim_date AS shipped ON shipped.date_key = f.shipped_date_key
JOIN dim_date AS delivered ON delivered.date_key = f.delivered_date_key
"""

# ジャンクディメンション: 値の種類が少ないフラグ類を 1 つの小さな表にまとめる。
# is_gift と payment_method はねぼすけ商店のデータには無い、説明用の仮の列。
JUNK_DIM_SQL = """
CREATE OR REPLACE TABLE dim_order_flags AS
SELECT row_number() OVER (ORDER BY payment_method, is_gift)::INTEGER AS flags_key, payment_method, is_gift
FROM (VALUES ('card'), ('cod'), ('bank')) AS p(payment_method)
CROSS JOIN (VALUES (true), (false)) AS g(is_gift)
"""

# 適合ディメンション: 行動ログのファクトも、同じ dim_date・dim_customer を使う。
FACT_EVENTS_SQL = """
CREATE OR REPLACE TABLE fact_events AS
SELECT d.date_key, COALESCE(c.customer_key, -1) AS customer_key, e.event_type, count(*) AS events
FROM (SELECT DISTINCT * FROM events) AS e
JOIN dim_date AS d ON d.date = CAST(e.event_time AS TIMESTAMP)::DATE
LEFT JOIN dim_customer AS c ON c.customer_id = e.customer_id
     AND CAST(e.event_time AS TIMESTAMP)::DATE >= c.valid_from
     AND CAST(e.event_time AS TIMESTAMP)::DATE < c.valid_to
GROUP BY ALL
"""

# ドリルアクロス: ファクトごとに同じ粒度（月 x 都道府県）へ集計してから、共通のキーでつなぐ。
DRILL_ACROSS_SQL = """
WITH s AS (
    SELECT d.year_month, c.prefecture, sum(f.sales_amount) AS sales
    FROM fact_order_items AS f
    JOIN dim_date AS d USING (date_key) JOIN dim_customer AS c USING (customer_key)
    JOIN dim_order_status AS st USING (status_key)
    WHERE st.is_sales GROUP BY 1, 2),
v AS (
    SELECT d.year_month, c.prefecture, sum(e.events) AS views
    FROM fact_events AS e
    JOIN dim_date AS d USING (date_key) JOIN dim_customer AS c USING (customer_key)
    WHERE e.event_type = 'view' GROUP BY 1, 2)
SELECT year_month, prefecture, s.sales, v.views
FROM s FULL JOIN v USING (year_month, prefecture)
ORDER BY 1, 2
"""

# やってはいけない形: 粒度の違うファクトを直接つなぐと、行が掛け算になって売上が水増しされる。
FAN_OUT_SQL = """
SELECT sum(f.sales_amount)
FROM fact_order_items AS f
JOIN dim_order_status AS st USING (status_key)
JOIN fact_events AS e ON e.customer_key = f.customer_key
WHERE st.is_sales
"""
TRUE_SALES_SQL = """
SELECT sum(f.sales_amount) FROM fact_order_items AS f
JOIN dim_order_status AS st USING (status_key) WHERE st.is_sales
"""

# ワイドテーブル（OBT）: ファクトとディメンションを全部つないだ 1 枚。読みやすいが、重複が増える。
OBT_SQL = """
CREATE OR REPLACE TABLE obt_order_items AS
SELECT f.order_id, f.line_no, d.date, d.year_month, d.is_weekend,
       c.customer_id, c.prefecture, p.name AS product_name, p.category,
       s.status, s.is_sales, f.quantity, f.unit_price, f.sales_amount
FROM fact_order_items AS f
JOIN dim_date AS d USING (date_key)
JOIN dim_customer AS c USING (customer_key)
JOIN dim_product AS p USING (product_key)
JOIN dim_order_status AS s USING (status_key)
"""


def build_all(con: duckdb.DuckDBPyConnection) -> None:
    from star_schema import execute_script

    build_star(con)
    for script in (SNOWFLAKE_SQL, PERIODIC_SNAPSHOT_SQL, FACT_EVENTS_SQL, OBT_SQL):
        execute_script(con, script)


if __name__ == "__main__":
    con = duckdb.connect()
    build_all(con)
    print(con.execute(SNOWFLAKE_QUERY).fetchall() == con.execute(STAR_CATEGORY_QUERY).fetchall())
    print(con.execute("SELECT count(*), max(cumulative_sales) FROM fact_customer_month_snapshot").fetchone())
    print(con.execute("SELECT snapshot_date_key, sum(cumulative_sales) FROM fact_customer_month_snapshot"
                      " GROUP BY 1 ORDER BY 1").fetchall())
    print(con.execute(TRUE_SALES_SQL).fetchone(), con.execute(FAN_OUT_SQL).fetchone())
    print(con.execute(DRILL_ACROSS_SQL).fetchall()[:3])
    for snapshot in fulfillment_demo(duckdb.connect()):
        print(snapshot)
    print(con.execute("SELECT count(*) FROM obt_order_items").fetchone(),
          con.execute("SELECT count(*) FROM fact_order_items").fetchone())
