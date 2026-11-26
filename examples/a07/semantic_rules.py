"""第7章: JSON Schema では書けない契約 (一意性・列同士の関係・他の表との参照) を SQL で確かめます。"""
import duckdb
import pyarrow as pa

UNIQUE_SQL = "SELECT count(*) - count(DISTINCT order_id) FROM orders"

TOTAL_SQL = """
SELECT count(*) FROM orders o
JOIN (SELECT order_id, sum(quantity * unit_price) AS lines_total FROM order_items GROUP BY order_id) i
  ON i.order_id = o.order_id
WHERE o.total_amount <> i.lines_total
"""

REFERENCE_SQL = "SELECT count(*) FROM orders WHERE customer_id NOT IN (SELECT customer_id FROM customers)"

RULES = {
    "order_id が一意": UNIQUE_SQL,
    "total_amount が明細の合計と一致": TOTAL_SQL,
    "customer_id が顧客表に存在": REFERENCE_SQL,
}


def load_tables(orders, order_items, customers):
    """レコードの一覧 (dict のリスト) から、DuckDB (メモリ上) に 3 つの表を作ります。"""
    con = duckdb.connect()
    for name, rows in [("orders", orders), ("order_items", order_items), ("customers", customers)]:
        con.register(name + "_arrow", pa.Table.from_pylist(rows))
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_arrow")
    return con


def run_rules(con):
    """規則ごとの違反件数を返します。全部 0 なら合格です。"""
    return {name: con.execute(sql).fetchone()[0] for name, sql in RULES.items()}
