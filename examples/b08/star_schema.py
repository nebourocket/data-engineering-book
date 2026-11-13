"""ねぼすけ商店の注文データから、スタースキーマ（ファクト 1 つとディメンション数個）を DuckDB に作ります。"""
import sys
from pathlib import Path

import duckdb
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.common.neboske_shop import generate  # noqa: E402

FAR_FUTURE = "9999-12-31"  # 「今も有効」を表す valid_to。履歴の区間は [valid_from, valid_to) の半開区間にする。


def load_sources(con: duckdb.DuckDBPyConnection) -> None:
    """業務システムの表（customers・products・orders・order_items・events）を作る。"""
    for name, rows in generate().items():
        con.register("_t", pa.Table.from_pylist(rows))
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _t")
        con.unregister("_t")


# 日付ディメンション: 1 日 1 行。DuckDB の range() で作る（PostgreSQL なら generate_series）。
DIM_DATE_SQL = """
CREATE OR REPLACE TABLE dim_date AS
SELECT strftime(d, '%Y%m%d')::INTEGER AS date_key,
       d::DATE AS date,
       year(d) AS year,
       month(d) AS month,
       strftime(d, '%Y-%m') AS year_month,
       isodow(d) AS iso_weekday,
       isodow(d) >= 6 AS is_weekend
FROM range(DATE '2026-01-01', DATE '2027-01-01', INTERVAL 1 DAY) AS t(d);
INSERT INTO dim_date VALUES (99991231, DATE '9999-12-31', 9999, 12, '9999-12', 0, false)
"""

# 商品ディメンション: 代理キー product_key は、業務システムの product_id とは別に振る。
DIM_PRODUCT_SQL = """
CREATE OR REPLACE TABLE dim_product AS
SELECT row_number() OVER (ORDER BY product_id)::INTEGER AS product_key,
       product_id, name, category
FROM products
"""

# 注文状態ディメンション: 表記ゆれを小文字にそろえ、「売上に数える状態か」を属性として持たせる。
DIM_ORDER_STATUS_SQL = """
CREATE OR REPLACE TABLE dim_order_status AS
SELECT row_number() OVER (ORDER BY status)::INTEGER AS status_key,
       status, status <> 'cancelled' AS is_sales
FROM (SELECT DISTINCT lower(status) AS status FROM orders)
"""

# 顧客ディメンション（タイプ 2 で履歴を持つ）。最初の版は登録日から有効。
DIM_CUSTOMER_SQL = f"""
CREATE OR REPLACE SEQUENCE customer_key_seq START 1;
CREATE OR REPLACE TABLE dim_customer (
    customer_key INTEGER, customer_id INTEGER, name VARCHAR, email VARCHAR, prefecture VARCHAR,
    valid_from DATE, valid_to DATE, is_current BOOLEAN);
INSERT INTO dim_customer VALUES (-1, -1, '不明', NULL, '不明', DATE '1900-01-01', DATE '{FAR_FUTURE}', true);
INSERT INTO dim_customer
SELECT nextval('customer_key_seq'), customer_id, name, email, prefecture,
       CAST(registered_at AS TIMESTAMP)::DATE, DATE '{FAR_FUTURE}', true
FROM customers ORDER BY customer_id
"""

# ファクト: 粒度は「注文明細の 1 行」。業務の言葉で先に決めてから、列を並べる。
FACT_ORDER_ITEMS_SQL = """
CREATE OR REPLACE TABLE fact_order_items AS
SELECT i.order_id, i.line_no,
       d.date_key,
       COALESCE(c.customer_key, -1) AS customer_key,
       p.product_key,
       s.status_key,
       i.quantity,
       i.unit_price,
       i.quantity * i.unit_price AS sales_amount
FROM order_items AS i
JOIN orders AS o USING (order_id)
JOIN dim_date AS d ON d.date = CAST(o.ordered_at AS TIMESTAMP)::DATE
LEFT JOIN dim_customer AS c ON c.customer_id = o.customer_id
     AND CAST(o.ordered_at AS TIMESTAMP)::DATE >= c.valid_from
     AND CAST(o.ordered_at AS TIMESTAMP)::DATE < c.valid_to
JOIN dim_product AS p ON p.product_id = i.product_id
JOIN dim_order_status AS s ON s.status = lower(o.status)
"""

# 業務の質問「月別・都道府県別・カテゴリ別の売上」に、結合 4 つで答える。
STAR_QUERY = """
SELECT d.year_month, c.prefecture, p.category, sum(f.sales_amount) AS sales
FROM fact_order_items AS f
JOIN dim_date AS d USING (date_key)
JOIN dim_customer AS c USING (customer_key)
JOIN dim_product AS p USING (product_key)
JOIN dim_order_status AS s USING (status_key)
WHERE s.is_sales
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
"""


def execute_script(con, script: str) -> None:
    for statement in script.split(";\n"):
        con.execute(statement)


def build_star(con: duckdb.DuckDBPyConnection) -> None:
    """ソースの読み込みから、ディメンション 4 つとファクト 1 つまでを作る。"""
    load_sources(con)
    for script in (DIM_DATE_SQL, DIM_PRODUCT_SQL, DIM_ORDER_STATUS_SQL, DIM_CUSTOMER_SQL,
                   FACT_ORDER_ITEMS_SQL):
        execute_script(con, script)


if __name__ == "__main__":
    con = duckdb.connect()
    build_star(con)
    for table in ("dim_date", "dim_product", "dim_order_status", "dim_customer", "fact_order_items"):
        print(table, con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    print(con.execute(STAR_QUERY).fetchall()[:3])
    print(con.execute("SELECT * FROM dim_order_status ORDER BY status_key").fetchall())
