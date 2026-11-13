"""第 5 章（準備編）の SQL を DuckDB に流して、結果と、本文に写した画面の出力が本物かを確かめます。"""
import csv
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
BOOK = ROOT / "book" / "start" / "s05-sql-1.md"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run_sql = _load("run_sql_s05", HERE / "run_sql.py")
make_tables = _load("make_tables_s05", HERE / "make_tables.py")
QUERIES = run_sql.split_queries((HERE / "queries.sql").read_text(encoding="utf-8"))
ERRORS = run_sql.split_queries((HERE / "errors.sql").read_text(encoding="utf-8"))


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute((HERE / "create_products.sql").read_text(encoding="utf-8"))
    yield con
    con.close()


def names(rows):
    return [r[0] for r in rows]


EXPECT = {
    "show_tables": lambda r: r == [("products",)],
    "describe_products": lambda r: [(x[0], x[1], x[3]) for x in r] == [
        ("product_id", "INTEGER", "PRI"), ("name", "VARCHAR", None), ("category", "VARCHAR", None),
        ("price", "INTEGER", None), ("stock", "INTEGER", None)],
    "all_rows": lambda r: len(r) == 9 and r[0] == (1, "枕", "寝具", 3200, 12),
    "pick_columns": lambda r: len(r) == 9 and r[0] == ("枕", 3200),
    "reorder_columns": lambda r: r[0] == (3200, "枕"),
    "expression": lambda r: r[1] == ("毛布", 5800, 11600),
    "alias_quoted": lambda r: r[0] == ("枕", 3200),
    "where_eq": lambda r: names(r) == ["コーヒー豆(標準)", "コーヒー豆(大)", "紅茶"],
    "where_cmp": lambda r: r == [("枕", 3200), ("毛布", 5800), ("光る目覚まし", 4500)],
    "where_ne": lambda r: len(r) == 6 and "枕" not in names(r),
    "where_and": lambda r: names(r) == ["枕", "アイマスク"],
    "where_or": lambda r: len(r) == 5,
    "where_not": lambda r: len(r) == 6,
    "where_paren": lambda r: names(r) == ["紅茶", "ステッカー"],
    "where_no_paren": lambda r: len(r) == 4 and "コーヒー豆(大)" in names(r),
    "where_in": lambda r: len(r) == 5,
    "where_between": lambda r: names(r) == ["コーヒー豆(標準)", "コーヒー豆(大)", "マグカップ"],
    "where_like_prefix": lambda r: names(r) == ["コーヒー豆(標準)", "コーヒー豆(大)"],
    "where_like_inner": lambda r: names(r) == ["アイマスク", "マグカップ"],
    "where_like_one": lambda r: r == [("紅茶",)],
    "string_case": lambda r: r == [(False,)],
    "order_asc": lambda r: [x[1] for x in r] == sorted(x[1] for x in r) and r[0] == ("ステッカー", 300),
    "order_desc": lambda r: r[0] == ("毛布", 5800) and r[-1] == ("ステッカー", 300),
    "order_two": lambda r: r[0] == ("毛布", "寝具", 5800) and r[3] == ("光る目覚まし", "目覚まし", 4500),
    "limit_top3": lambda r: r == [("毛布", 5800), ("光る目覚まし", 4500), ("枕", 3200)],
    "limit_only": lambda r: r == [("枕", 3200), ("毛布", 5800), ("アイマスク", 900)],
    "full_query": lambda r: r == [("毛布", 5800), ("枕", 3200), ("コーヒー豆(大)", 2800)],
    "lowercase_ok": lambda r: r == [("ステッカー", 300), ("マグカップ", 1500)],
    "upper_names": lambda r: r == [("ステッカー", 300)],
    "one_line": lambda r: names(r) == ["ステッカー", "紅茶", "アイマスク"],
    "with_comment": lambda r: r == [("毛布", 5800), ("光る目覚まし", 4500), ("枕", 3200)],
}

ERROR_EXPECT = {
    "typo_keyword": (duckdb.ParserException, 'syntax error at or near "SELCT"'),
    "typo_column": (duckdb.BinderException, 'Referenced column "nmae" not found'),
    "typo_table": (duckdb.CatalogException, 'Did you mean "products"?'),
    "double_quote": (duckdb.BinderException, 'Referenced column "飲み物" not found'),
    "fullwidth_quote": (duckdb.BinderException, "‘飲み物’"),
    "dangling_and": (duckdb.ParserException, 'syntax error at or near ";"'),
    "duplicate_key": (duckdb.ConstraintException, "violates primary key constraint"),
    "create_twice": (duckdb.CatalogException, 'Table with name "products" already exists'),
    "not_a_number": (duckdb.ConversionException, "Could not convert string 'ten'"),
}


EXERCISES = run_sql.split_queries((HERE / "exercises.sql").read_text(encoding="utf-8"))


def test_exercise_answers(con):
    """練習問題の解答例が、本文で言っている結果になります。"""
    def rows(name):
        return con.execute(EXERCISES[name]).fetchall()

    assert rows("ex1") == [("毛布", 5), ("光る目覚まし", 8), ("紅茶", 0)]
    assert names(rows("ex2")) == ["毛布", "光る目覚まし", "枕", "マグカップ"]
    assert sorted(names(rows("ex3"))) == sorted(["コーヒー豆(標準)", "コーヒー豆(大)", "毛布", "紅茶"])
    three = [("ステッカー", 300), ("紅茶", 800), ("アイマスク", 900)]
    assert rows("ex4_limit") == three
    assert rows("ex4_between") == three
    rows("ex5")
    assert con.execute("SELECT count(*) FROM products").fetchall() == [(10,)]
    with pytest.raises(duckdb.ConstraintException):
        con.execute(EXERCISES["ex5"])
    assert rows("ex6") == [("マグカップ", 1500), ("ステッカー", 300)]


def test_exercise_six_errors_come_one_at_a_time(con):
    """問 6 の 3 つの間違いは、1 つ直すごとに次のエラーが出ます。"""
    bad = "SELCT name, price FROM products WHERE category = \"雑貨\" ORDER BY price DESC LIMT 2;"
    with pytest.raises(duckdb.ParserException, match="SELCT"):
        con.execute(bad)
    bad = bad.replace("SELCT", "SELECT")
    with pytest.raises(duckdb.ParserException, match="LIMT"):
        con.execute(bad)
    bad = bad.replace("LIMT", "LIMIT")
    with pytest.raises(duckdb.BinderException, match="雑貨"):
        con.execute(bad)


def test_every_query_has_an_expectation():
    assert set(QUERIES) == set(EXPECT)
    assert set(ERRORS) == set(ERROR_EXPECT) | {"missing_comma"}


@pytest.mark.parametrize("name", list(EXPECT))
def test_query(con, name):
    rows = con.execute(QUERIES[name]).fetchall()
    assert EXPECT[name](rows), rows


@pytest.mark.parametrize("name", list(ERROR_EXPECT))
def test_error(con, name):
    exc, fragment = ERROR_EXPECT[name]
    with pytest.raises(exc, match=re.escape(fragment)):
        con.execute(ERRORS[name])


def test_missing_comma_is_not_an_error(con):
    """カンマを忘れても、name が price という別名の列として動いてしまいます。"""
    assert con.execute(ERRORS["missing_comma"]).fetchall() == [("枕",), ("毛布",)]
    assert con.execute(ERRORS["missing_comma"]).description[0][0] == "price"


def test_products_has_nine_rows_and_unique_key(con):
    assert con.execute("SELECT count(*), count(DISTINCT product_id) FROM products").fetchall() == [(9, 9)]


def test_csv_tables_match_database(tmp_path):
    make_tables.write_all(tmp_path)
    for generated in tmp_path.glob("*.csv"):
        committed = ROOT / "data" / "tables" / generated.name
        assert committed.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8"), generated.name


def _cli(db, sql_file, name=None):
    """読者と同じ方法（run_sql.py）で流し、画面に出る文字を返します。"""
    cmd = [sys.executable, str(HERE / "run_sql.py"), str(db), str(sql_file)] + ([name] if name else [])
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return (done.stdout + done.stderr).rstrip("\n")


def test_screen_output_in_book_is_real(tmp_path):
    """本文の ```text のうち、表やエラーの画面は、run_sql.py の本物の出力と同じでなければなりません。"""
    db = tmp_path / "shop.duckdb"
    _cli(db, HERE / "create_products.sql")
    real = {_cli(db, HERE / "queries.sql", n) for n in QUERIES}
    real |= {_cli(db, HERE / "errors.sql", n) for n in ERRORS}
    blocks = [textwrap.dedent(m.group(2)) for m in re.finditer(
        r"^( *)```text\n(.*?)^\1```", BOOK.read_text(encoding="utf-8"), flags=re.S | re.M)]
    screens = [b.rstrip("\n") for b in blocks if b.startswith("┌") or "Error:" in b]
    assert len(screens) >= 20
    for block in screens:
        assert block in real, block[:80]
