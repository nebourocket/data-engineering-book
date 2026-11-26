"""SQL ファイルを DuckDB のデータベースファイルに流して、結果を表示します。

使い方: python examples/s05/run_sql.py practice.duckdb 流す.sql [名前 ...]
SQL ファイルは「-- name: 名前」の行でひとまとまりに区切れます。名前を渡すと、そのまとまりだけを流します。
名前を渡さなければファイル全体を流します。SELECT の結果は表で表示し、エラーは内容を表示して終わります。
"""
import re
import sys
from pathlib import Path

import duckdb


def split_queries(text: str) -> dict[str, str]:
    """「-- name: 名前」の行で区切って {名前: SQL} を返します。"""
    parts = re.split(r"^-- name: (\S+)\n", text, flags=re.M)
    return {name: sql.strip() for name, sql in zip(parts[1::2], parts[2::2])}


def run(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """SQL を 1 文ずつ流し、SELECT 系の結果だけを表示します。"""
    for statement in duckdb.extract_statements(sql):
        result = con.sql(statement.query)
        if statement.type == duckdb.StatementType.SELECT:
            result.show()


def main(db: str, sql_file: str, names: list[str]) -> int:
    text = Path(sql_file).read_text(encoding="utf-8")
    queries = split_queries(text) if "-- name:" in text else {"all": text}
    con = duckdb.connect(db)
    try:
        for name in names or list(queries):
            run(con, queries[name])
    except duckdb.Error as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
