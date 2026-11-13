"""第 6 章（準備編）の SQL を DuckDB に流して、結果と、本文に写した画面の出力が本物かを確かめます。"""
import importlib.util
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
RUNNER = ROOT / "examples" / "s05" / "run_sql.py"
BOOK = ROOT / "book" / "start" / "s06-sql-2.md"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run_sql = _load("run_sql_s06", RUNNER)
make_tables = _load("make_tables_s06", HERE / "make_tables.py")
QUERIES = run_sql.split_queries((HERE / "queries.sql").read_text(encoding="utf-8"))
ERROR_NAMES = {
    "group_by_wrong": ("must appear in the GROUP BY clause", duckdb.BinderException),
    "where_aggregate_wrong": ("WHERE clause cannot contain aggregates", duckdb.BinderException),
    "join_no_on": ('syntax error at or near ";"', duckdb.ParserException),
    "join_ambiguous": ("Ambiguous reference to column name", duckdb.BinderException),
}


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute((HERE / "setup.sql").read_text(encoding="utf-8"))
    yield con
    con.close()


def names(rows):
    return [r[0] for r in rows]


EXPECT = {
    "all_customers": lambda r: len(r) == 4 and r[2] == (3, "高橋 健", "東京", None, None) and r[1][3] == "",
    "all_orders": lambda r: len(r) == 6 and r[0] == (101, 1, 3200),
    "count_all": lambda r: r == [(6,)],
    # 手計算: 3200 + 900 + 5800 + 1200 + 2800 + 1500 = 15400
    "aggregates": lambda r: r == [(6, 15400, 900, 5800)],
    "average": lambda r: r[0][1] == 2566.7 and abs(r[0][0] - 15400 / 6) < 1e-9,
    "sum_where": lambda r: r == [(5500,)],
    "group_by": lambda r: r == [(1, 2, 4100), (2, 1, 5800), (3, 3, 5500)],
    "group_by_where": lambda r: r == [(1, 1, 3200), (2, 1, 5800), (3, 3, 5500)],
    "group_by_having": lambda r: r == [(1, 2, 4100), (3, 3, 5500)],
    "where_and_having": lambda r: r == [(3, 3, 5500)],
    "join_inner": lambda r: len(r) == 6 and r[0] == (1, "佐藤 太郎", 101, 3200) and 4 not in [x[0] for x in r],
    "join_left": lambda r: len(r) == 7 and r[-1] == (4, "田中 美咲", None, None),
    "count_customers": lambda r: r == [(4,)],
    "join_count_inner": lambda r: r == [(6,)],
    "join_count_left": lambda r: r == [(7,)],
    "join_on_swapped": lambda r: len(r) == 6 and r[0] == (1, "佐藤 太郎", 101, 3200),
    "join_star": lambda r: len(r) == 6 and len(r[0]) == 8,
    "cross_rows": lambda r: r == [(24,)],  # 4 x 6
    "left_where_wrong": lambda r: [x[1] for x in r] == [101, 103, 104, 105, 106],
    "left_on_right": lambda r: r == [("佐藤 太郎", 101, 3200), ("鈴木 花子", 103, 5800), ("高橋 健", 104, 1200),
                                     ("高橋 健", 105, 2800), ("高橋 健", 106, 1500), ("田中 美咲", None, None)],
    "fanout_wrong": lambda r: r == [(700,)],  # 100 x 2 + 300 + 200
    "fanout_ok": lambda r: r == [(600,)],
    "count_distinct": lambda r: r == [(6, 3)],
    "group_prefecture": lambda r: r == [("大阪", 1, 1, 300.0), ("東京", 2, 1, 100.0), ("石川", 1, 1, 200.0)],
    "order_null_asc": lambda r: r == [(1, 100), (4, 200), (2, 300), (3, None)],
    "order_null_desc": lambda r: r == [(2, 300), (4, 200), (1, 100), (3, None)],
    "join_no_orders": lambda r: r == [("田中 美咲",)],
    "join_group": lambda r: r == [("佐藤 太郎", 2, 4100), ("田中 美咲", 0, None), ("鈴木 花子", 1, 5800),
                                  ("高橋 健", 3, 5500)],
    "null_show": lambda r: r[1] == (2, "", 300) and r[2] == (3, None, None),
    "null_arith": lambda r: r == [(None, None, True)],
    "null_equal_wrong": lambda r: r == [],
    "null_is": lambda r: r == [("高橋 健",)],
    "null_not": lambda r: names(r) == ["佐藤 太郎", "鈴木 花子", "田中 美咲"],
    "empty_string": lambda r: r == [("鈴木 花子",)],
    "null_vanishes_ge": lambda r: r == [("鈴木 花子", 300), ("田中 美咲", 200)],
    "null_vanishes_lt": lambda r: r == [("佐藤 太郎", 100)],
    "count_variants": lambda r: r == [(4, 3, 3)],
    "avg_points": lambda r: r == [(200.0, 600, 3)],
    "coalesce_points": lambda r: r == [(150.0,)],
    "subquery_scalar": lambda r: r == [(101, 3200), (103, 5800), (105, 2800)],
    "subquery_in": lambda r: names(r) == ["佐藤 太郎", "鈴木 花子", "高橋 健"],
    "subquery_from": lambda r: r == [(5800,)],
}


EXERCISES = run_sql.split_queries((HERE / "exercises.sql").read_text(encoding="utf-8"))


def test_exercise_answers(con):
    """練習問題の解答例が、本文で言っている結果になります。"""
    def rows(name):
        return con.execute(EXERCISES[name]).fetchall()

    assert rows("ex1") == [(3, 11800)]
    assert rows("ex2") == [(1, 3200), (2, 5800), (3, 2800)]
    assert rows("ex3") == [(2, 5800), (3, 5500)]
    assert rows("ex4") == [("佐藤 太郎", 101, 3200), ("佐藤 太郎", 102, 900), ("高橋 健", 104, 1200),
                           ("高橋 健", 105, 2800), ("高橋 健", 106, 1500)]
    assert rows("ex5") == [("大阪", 1, 300.0), ("東京", 2, 100.0), ("石川", 1, 200.0)]
    assert rows("ex6") == [(103, 5800)]
    assert rows("ex7") == [("田中 美咲", "石川")]
    assert rows("ex8") == [("高橋 健", 3), ("佐藤 太郎", 2), ("鈴木 花子", 1), ("田中 美咲", 0)]
    assert rows("ex9") == [("鈴木 花子", 5800), ("高橋 健", 5500)]


def test_swapped_on_gives_same_rows(con):
    assert con.execute(QUERIES["join_on_swapped"]).fetchall() == con.execute(QUERIES["join_inner"]).fetchall()


def test_list_functions_keep_null(con):
    """ほとんどの集計関数は NULL を無視しますが、list は NULL を含めます。"""
    assert con.execute("SELECT list(points) FROM customers").fetchall() == [([100, 300, None, 200],)]
    assert con.execute("SELECT count(points), sum(points) FROM customers").fetchall() == [(3, 600)]


def test_every_query_has_an_expectation():
    assert set(QUERIES) == set(EXPECT) | set(ERROR_NAMES)


@pytest.mark.parametrize("name", list(EXPECT))
def test_query(con, name):
    rows = con.execute(QUERIES[name]).fetchall()
    assert EXPECT[name](rows), rows


@pytest.mark.parametrize("name", list(ERROR_NAMES))
def test_error(con, name):
    fragment, exc = ERROR_NAMES[name]
    with pytest.raises(exc, match=re.escape(fragment)):
        con.execute(QUERIES[name])


def test_join_rows_match_python_loop(con):
    """JOIN の結果を、Python の二重ループで数えた行数と見比べます（INNER は 6、LEFT は 7）。"""
    customers = con.execute("SELECT customer_id FROM customers").fetchall()
    orders = con.execute("SELECT customer_id FROM orders").fetchall()
    inner = sum(1 for c in customers for o in orders if c == o)
    unmatched = sum(1 for c in customers if c not in orders)
    assert (inner, inner + unmatched) == (6, 7)


def test_csv_tables_match_database(tmp_path):
    make_tables.write_all(tmp_path)
    for generated in tmp_path.glob("*.csv"):
        committed = ROOT / "data" / "tables" / generated.name
        assert committed.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8"), generated.name


def _cli(db, sql_file, name=None):
    """読者と同じ方法（run_sql.py）で流し、画面に出る文字を返します。"""
    cmd = [sys.executable, str(RUNNER), str(db), str(sql_file)] + ([name] if name else [])
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return (done.stdout + done.stderr).rstrip("\n")


def test_screen_output_in_book_is_real(tmp_path):
    """本文の ```text のうち、表やエラーの画面は、run_sql.py の本物の出力と同じでなければなりません。"""
    db = tmp_path / "shop.duckdb"
    _cli(db, HERE / "setup.sql")
    real = {_cli(db, HERE / "queries.sql", n) for n in QUERIES}
    blocks = [textwrap.dedent(m.group(2)) for m in re.finditer(
        r"^( *)```text\n(.*?)^\1```", BOOK.read_text(encoding="utf-8"), flags=re.S | re.M)]
    screens = [b.rstrip("\n") for b in blocks if b.startswith("┌") or "Error:" in b]
    assert len(screens) >= 20
    for block in screens:
        assert block in real, block[:80]
