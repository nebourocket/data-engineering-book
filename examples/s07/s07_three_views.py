"""同じ 2 行のデータを、CSV・JSON・表 (DuckDB) で並べて見ます。"""
import csv
import io
import json

import duckdb

rows = [
    {"order_id": 1001, "customer": "佐藤 太郎", "coupon": None},
    {"order_id": 1002, "customer": "鈴木 花子", "coupon": "WELCOME"},
]

buffer = io.StringIO(newline="")
writer = csv.DictWriter(buffer, fieldnames=["order_id", "customer", "coupon"], lineterminator="\n")
writer.writeheader()
writer.writerows(rows)
print(buffer.getvalue())

print(json.dumps(rows, ensure_ascii=False))

con = duckdb.connect()
con.execute("CREATE TABLE orders (order_id INTEGER, customer VARCHAR, coupon VARCHAR)")
con.executemany("INSERT INTO orders VALUES (?, ?, ?)",
                [(r["order_id"], r["customer"], r["coupon"]) for r in rows])
con.sql("SELECT * FROM orders").show()
