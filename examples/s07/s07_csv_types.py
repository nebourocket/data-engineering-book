"""CSV は全部ただの文字です。数として読むと先頭のゼロが消え、日付は読み方で変わります。"""
import tempfile
from datetime import datetime
from pathlib import Path

import duckdb

with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "items.csv"
    path.write_text("code,name\n00123,アイマスク\n04567,置き時計\n", encoding="utf-8")

    # 型を決めずに読む。DuckDB 2.0 で試すと、ゼロで始まる値は文字のまま残った
    print(duckdb.sql(f"SELECT code, typeof(code) AS type FROM read_csv('{path}')").fetchall())
    # 数 (INTEGER) と決めて読むと、先頭のゼロが消える
    column_types = {"code": "INTEGER"}
    print(duckdb.sql(f"SELECT code, typeof(code) AS type FROM read_csv('{path}', types={column_types})").fetchall())

# 数にした値を文字に戻しても、ゼロは戻らない
print(str(int("00123")))

# 日付の見え方。「03/04/2026」は、読み方で 3 月 4 日にも 4 月 3 日にもなる
text = "03/04/2026"
print(datetime.strptime(text, "%m/%d/%Y").date())
print(datetime.strptime(text, "%d/%m/%Y").date())
