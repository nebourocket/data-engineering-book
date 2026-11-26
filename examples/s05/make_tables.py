"""第 5 章の表（data/tables/s05-*.csv のうち、データを含むもの）を DuckDB の結果から作ります。

本文の表を手で写すと数字が揺れるので、products の中身はこのスクリプトが CSV に書き出します。
"""
import csv
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
TABLES = HERE.parents[1] / "data" / "tables"

# 作る CSV 名と、その中身を返す SQL
TABLE_QUERIES = {
    "s05-products": "SELECT * FROM products ORDER BY product_id",
}


def build_connection() -> duckdb.DuckDBPyConnection:
    """メモリ上のデータベースに products を作って返します。"""
    con = duckdb.connect()
    con.execute((HERE / "create_products.sql").read_text(encoding="utf-8"))
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
