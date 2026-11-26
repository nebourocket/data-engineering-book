"""ねぼすけ商店の売上を、スター・ワイドテーブル (OBT)・Data Vault の 3 つのモデルで作ります (DuckDB)。"""
import duckdb
import pyarrow as pa

from neboske_shop import generate

SOURCE_SQL = """
CREATE TABLE customers AS
SELECT c.customer_id + k.k * 1000 AS customer_id, c.name, c.email, c.prefecture, c.registered_at
FROM base_customers c, range({scale}) AS k(k);
CREATE TABLE products AS SELECT * FROM base_products;
CREATE TABLE orders AS
SELECT o.order_id + k.k * 10000 AS order_id, o.customer_id + k.k * 1000 AS customer_id,
       o.ordered_at, lower(o.status) AS status,
       400 + 100 * (o.order_id % 3) AS shipping_fee
FROM base_orders o, range({scale}) AS k(k);
CREATE TABLE order_items AS
SELECT i.order_id + k.k * 10000 AS order_id, i.line_no, i.product_id, i.quantity, i.unit_price
FROM base_items i, range({scale}) AS k(k);
CREATE TABLE events AS
SELECT DISTINCT e.event_id + k.k * 10000 AS event_id, e.customer_id + k.k * 1000 AS customer_id,
       e.event_type, e.event_time
FROM base_events e, range({scale}) AS k(k)
"""


def load_source(scale):
    """元データを scale 倍にした DuckDB (メモリ上) を返します。

    顧客と注文が scale 倍になり、商品 (52 件) は増えません。scale=10 なら注文は約 3 万件です。
    """
    shop = generate()
    con = duckdb.connect()
    # 重複登録の顧客 (customer_id が 500 を超える) は 1,000 刻みの ID 空間に収まる
    for name, key in [("base_customers", "customers"), ("base_products", "products"),
                      ("base_orders", "orders"), ("base_items", "order_items"),
                      ("base_events", "events")]:
        con.register(name + "_arrow", pa.Table.from_pylist(shop[key]))
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_arrow")
    con.execute(SOURCE_SQL.format(scale=int(scale)))
    return con


STAR_SQL = """
CREATE TABLE dim_customer AS
SELECT row_number() OVER (ORDER BY customer_id) AS customer_key, customer_id, name, prefecture FROM customers;
CREATE TABLE dim_product AS
SELECT row_number() OVER (ORDER BY product_id) AS product_key, product_id, name AS product_name, category
FROM base_products;
CREATE TABLE dim_date AS
SELECT d::date AS date_key, strftime(d, '%Y-%m') AS month
FROM generate_series(DATE '2026-01-01', DATE '2026-12-31', INTERVAL 1 DAY) AS t(d);
CREATE TABLE fact_sales AS
SELECT i.order_id, i.line_no, dc.customer_key, dp.product_key, o.ordered_at::date AS date_key,
       o.status, o.shipping_fee, i.quantity, i.quantity * i.unit_price AS amount
FROM order_items i
JOIN orders o USING (order_id)
JOIN dim_customer dc ON dc.customer_id = o.customer_id
JOIN dim_product dp ON dp.product_id = i.product_id
"""

OBT_SQL = """
CREATE TABLE obt_sales AS
SELECT f.order_id, f.line_no, f.date_key, d.month, f.status, f.shipping_fee,
       c.customer_id, c.name AS customer_name, c.prefecture,
       p.product_name, p.category, f.quantity, f.amount
FROM fact_sales f
JOIN dim_customer c USING (customer_key)
JOIN dim_product p USING (product_key)
JOIN dim_date d USING (date_key)
"""


def build_star(con):
    con.execute(STAR_SQL)


def build_obt(con):
    con.execute(OBT_SQL)


REVENUE_STAR = """
SELECT d.month, c.prefecture, p.category, sum(f.amount) AS revenue
FROM fact_sales f
JOIN dim_customer c USING (customer_key)
JOIN dim_product p USING (product_key)
JOIN dim_date d USING (date_key)
WHERE f.status <> 'cancelled'
GROUP BY ALL ORDER BY ALL
"""
REVENUE_OBT = """
SELECT month, prefecture, category, sum(amount) AS revenue
FROM obt_sales WHERE status <> 'cancelled'
GROUP BY ALL ORDER BY ALL
"""
