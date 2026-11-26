"""ねぼすけ商店の注文 (JSON) を表にして、SQL で集計します。"""
import json
from pathlib import Path

import duckdb

from s07_flatten import flatten

HERE = Path(__file__).resolve().parent

data = json.loads((HERE / "s07_shop_orders.json").read_text(encoding="utf-8"))
rows = flatten(data)

con = duckdb.connect()
con.execute("""
CREATE TABLE order_items (
    order_id INTEGER, customer VARCHAR, prefecture VARCHAR, coupon VARCHAR,
    product VARCHAR, price INTEGER, quantity INTEGER
)
""")
con.executemany(
    "INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?, ?)",
    [tuple(row.values()) for row in rows],
)

print("顧客ごとの合計金額")
con.sql("""
SELECT customer, sum(price * quantity) AS total
FROM order_items
GROUP BY customer
ORDER BY total DESC
""").show()

print("商品ごとの売れた個数")
con.sql("""
SELECT product, sum(quantity) AS sold
FROM order_items
GROUP BY product
ORDER BY sold DESC, product
""").show()

# 注文の件数は、行 (商品) の数ではなく、注文番号の種類の数で数える
print(con.sql("SELECT count(*) AS rows, count(DISTINCT order_id) AS orders FROM order_items").fetchall())
