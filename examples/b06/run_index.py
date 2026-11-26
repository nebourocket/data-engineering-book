"""インデックスの実験（duckdb_index.sql / pg_index.sql）を上から順に流して表示します。

使い方:
  python examples/b06/run_index.py duckdb       # メモリ上の DuckDB で動かします
  PG_DSN=postgresql://deb:deb@localhost:5432/deb python examples/b06/run_index.py postgres
PostgreSQL は README の手順で docker compose を起動してから流します。一時テーブルを使うので、
実験が終わると（接続を閉じると）表は消えます。
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent


def split_queries(text: str) -> dict[str, str]:
    """「-- name: 名前」で区切って {名前: SQL} を返します。"""
    parts = re.split(r"^-- name: (\S+)\n", text, flags=re.M)
    return {name: sql.strip() for name, sql in zip(parts[1::2], parts[2::2])}


def run_duckdb(path: Path) -> dict[str, str]:
    import duckdb

    con = duckdb.connect()
    out = {}
    for name, sql in split_queries(path.read_text(encoding="utf-8")).items():
        rows = con.execute(sql).fetchall()
        # EXPLAIN 系は 2 列目に計画の文字列が入っている
        out[name] = rows[0][-1] if sql.startswith("EXPLAIN") else str(rows)
    return out


def run_postgres(path: Path, dsn: str) -> dict[str, str]:
    import psycopg

    out = {}
    with psycopg.connect(dsn, autocommit=True) as con:
        for name, sql in split_queries(path.read_text(encoding="utf-8")).items():
            cur = con.execute(sql)
            out[name] = "\n".join(r[0] for r in cur.fetchall()) if cur.description else ""
    return out


if __name__ == "__main__":
    if sys.argv[1] == "duckdb":
        result = run_duckdb(HERE / "duckdb_index.sql")
    else:
        result = run_postgres(HERE / "pg_index.sql", os.environ["PG_DSN"])
    for name, text in result.items():
        print(f"-- {name}\n{text}\n")
