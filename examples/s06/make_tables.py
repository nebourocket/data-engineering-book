"""第 6 章の表（data/tables/s06-*.csv のうち、データを含むもの）を DuckDB の結果から作ります。

JOIN の前後の表は、手で写すと行が合わなくなるので、このスクリプトが CSV に書き出します。
"""
import csv
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
TABLES = HERE.parents[1] / "data" / "tables"

# 作る CSV 名と、その中身を返す SQL
TABLE_QUERIES = {
    "s06-customers": "SELECT customer_id, name, prefecture FROM customers ORDER BY customer_id",
    "s06-orders": "SELECT * FROM orders ORDER BY order_id",
    "s06-join-inner": """
        SELECT c.customer_id, c.name, o.order_id, o.amount
        FROM customers AS c INNER JOIN orders AS o ON o.customer_id = c.customer_id
        ORDER BY o.order_id""",
    "s06-join-left": """
        SELECT c.customer_id, c.name, o.order_id, o.amount
        FROM customers AS c LEFT JOIN orders AS o ON o.customer_id = c.customer_id
        ORDER BY c.customer_id, o.order_id""",
}


def build_connection() -> duckdb.DuckDBPyConnection:
    """メモリ上のデータベースに customers と orders を作って返します。"""
    con = duckdb.connect()
    con.execute((HERE / "setup.sql").read_text(encoding="utf-8"))
    return con


def render(con: duckdb.DuckDBPyConnection, sql: str) -> list[list[str]]:
    """SQL の結果を、見出し付きの文字列の行にします。NULL は NULL と書きます。"""
    cursor = con.execute(sql)
    header = [column[0] for column in cursor.description]
    rows = [["NULL" if v is None else str(v) for v in row] for row in cursor.fetchall()]
    return [header] + rows


def write_all(out_dir: Path = TABLES) -> None:
    con = build_connection()
    for name, sql in TABLE_QUERIES.items():
        with open(out_dir / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
            csv.writer(f, lineterminator="\n").writerows(render(con, sql))


if __name__ == "__main__":
    write_all()
