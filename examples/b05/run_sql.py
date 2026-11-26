"""SQL ファイルを DuckDB で実行して結果を表示します。

使い方: python examples/b05/run_sql.py examples/b05/queries.sql [クエリ名 ...]
ファイルは「-- name: 名前」の行でクエリを区切ります。名前を渡すとそのクエリだけ実行します。
カレントディレクトリに shop.duckdb が無ければ、ねぼすけ商店のデータで作ります。
"""
import re
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import write_duckdb  # noqa: E402


def split_queries(text: str) -> dict[str, str]:
    """「-- name: 名前」で区切って {名前: SQL} を返します。"""
    parts = re.split(r"^-- name: (\S+)\n", text, flags=re.M)
    return {name: sql.strip() for name, sql in zip(parts[1::2], parts[2::2])}


if __name__ == "__main__":
    db = Path("shop.duckdb")
    if not db.exists():
        write_duckdb(db)
    queries = split_queries(Path(sys.argv[1]).read_text(encoding="utf-8"))
    con = duckdb.connect(str(db))
    for name in sys.argv[2:] or queries:
        print(f"-- {name}")
        con.sql(queries[name]).show()
