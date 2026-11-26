"""第 5 章の SQL を、ねぼすけ商店の DuckDB に流して結果を確かめます。"""
import importlib.util
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).parent
COMMON = HERE.parent / "common"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shop = _load("neboske_shop_b05", COMMON / "neboske_shop.py")
run_sql = _load("run_sql_b05", HERE / "run_sql.py")
QUERIES = run_sql.split_queries((HERE / "queries.sql").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    path = tmp_path_factory.mktemp("b05") / "shop.duckdb"
    shop.write_duckdb(path)
    con = duckdb.connect(str(path))
    yield con
    con.close()


def rows(con, name):
    return con.execute(QUERIES[name]).fetchall()


def scalar(con, name):
    return rows(con, name)[0][0]


def test_every_query_has_an_expectation():
    assert set(QUERIES) == set(EXPECT)


EXPECT = {
    "describe_orders": lambda r: [x[0] for x in r] == ["order_id", "customer_id", "ordered_at", "status"],
    "first_orders": lambda r: r[0] == (1, 122, "2026-02-24 13:22:12", "shipped") and len(r) == 3,
    "tokyo": lambda r: [x[0] for x in r] == [8, 17, 28, 43, 47],
    "count_tokyo": lambda r: r == [(44,)],
    "march_orders": lambda r: len(r) == 3 and r[0][0] == 2283,
    "like_coffee": lambda r: r == [("コーヒー豆(標準)",), ("コーヒー豆(大)",)],
    "nulls_order": lambda r: r == [(2, None), (26, None), (36, None)],
    "null_logic": lambda r: r == [(None, True, None, False, True)],
    "eq_null": lambda r: r == [(0,)],
    "is_null": lambda r: r == [(20,)],
    "neq_email": lambda r: r == [(484,)],
    "neq_email_fixed": lambda r: r == [(504,)],
    "count_variants": lambda r: r == [(505, 485, 480)],
    "not_in_trap": lambda r: r == [(0,)],
    "not_exists_ok": lambda r: r == [(504,)],
    "group_status": lambda r: dict(r) == {"delivered": 977, "shipped": 925, "cancelled": 528, "placed": 511, "SHIPPED": 59},
    "group_status_lower": lambda r: dict(r) == {"shipped": 984, "delivered": 977, "cancelled": 528, "placed": 511},
    "having_pref": lambda r: r == [("愛知", 59), ("福岡", 57)],
    "revenue_by_category": lambda r: r[0] == ("飲み物", 1784, 10944850) and sum(x[2] for x in r) == 41665750,
    "left_anti": lambda r: r == [(261, "渡辺結衣")],
    "left_on_cond": lambda r: r == [(699,)],
    "left_where_cond": lambda r: r == [(528,)],
    "full_join": lambda r: r == [(1, 0, 3001)],
    "cross_join": lambda r: r == [(50,)],
    "fanout_count": lambda r: r == [(7469, 3000)],
    "fanout_two": lambda r: r == [(3, 11, 33)],
    "fanout_fixed": lambda r: r == [(122, 3, 11)],
    "dup_email": lambda r: len(r) == 5 and r[0] == (165, 505, "user0165@example.com"),
    "case_band": lambda r: r == [("低価格", 10), ("中価格", 18), ("高価格", 24)],
    "case_status": lambda r: r == [(528, 3000, 17.6)],
    "typeof_time": lambda r: r == [("VARCHAR", "TIMESTAMP")],
    "date_funcs": lambda r: str(r[0][1]) == "2026-02-01 00:00:00" and str(r[0][2]) == "2026-03-03",
    "monthly_orders": lambda r: [x[1] for x in r] == [163, 497, 820, 847, 518, 155] and sum(x[1] for x in r) == 3000,
    "late_events": lambda r: r == [(122,)],
    "alias_where": lambda r: r == [(11700,)],
    "slash": lambda r: r == [(3.5, 3)],
    "scalar_sub": lambda r: r[0] == ("シリアル(標準)", 5850),
    "exists_cancelled": lambda r: r == [(334,)],
    "from_sub": lambda r: r == [(2.49,)],
    "union_distinct": lambda r: r == [(505,)],
    "union_all": lambda r: r == [(7040,)],
    "coalesce_email": lambda r: r == [(2, "(未登録)"), (26, "(未登録)"), (36, "(未登録)")],
    "nullif_ratio": lambda r: len(r) == 10 and r[0] == (1, 1, 2, 0.5) and r[6][3] == 2.0,
    "clean_values": lambda r: r == [("090-1234-5678", "09012345678", 12, None)],
    "cast_error": lambda r: True,  # 実行すると失敗する例（test_cast_error で確かめる）
    "distinct_pref": lambda r: len(r) == 10,
    "except_customers": lambda r: r == [(261,)],
    "intersect_customers": lambda r: r == [(504,)],
}


@pytest.mark.parametrize("name", sorted(set(QUERIES) - {"cast_error"}))
def test_query(con, name):
    assert EXPECT[name](rows(con, name)), rows(con, name)


def test_cast_error(con):
    """CAST は 1 件でも変換できないと全体が止まる。TRY_CAST は NULL にする。"""
    with pytest.raises(duckdb.ConversionException, match="Could not convert string '12a'"):
        con.execute(QUERIES["cast_error"])


def test_ddl_in_order(tmp_path):
    """表を作る・書き換える例。上から順に流す必要があるので、専用の DB で試す。"""
    path = tmp_path / "shop.duckdb"
    shop.write_duckdb(path)
    con = duckdb.connect(str(path))
    ddl = run_sql.split_queries((HERE / "ddl.sql").read_text(encoding="utf-8"))
    for name, sql in ddl.items():
        if name == "ddl_duplicate_key_error":
            with pytest.raises(duckdb.ConstraintException, match="duplicate key"):
                con.execute(sql)
            continue
        got = con.execute(sql).fetchall()
        if name == "ddl_create_as":
            assert got == [(12,)]
        elif name == "ddl_count":
            assert got == [(12,)]
        elif name == "ddl_check":
            assert got == [(999, "テスト商品", 200)]
        elif name == "ddl_view_count":
            assert got == [(10,)]
    assert con.execute("SELECT count(*) FROM my_products").fetchone() == (12,)
    # 元の products は変わっていない
    assert con.execute("SELECT count(*) FROM products").fetchone() == (52,)
    con.close()


EXERCISES = run_sql.split_queries((HERE / "exercises.sql").read_text(encoding="utf-8"))


def test_exercises(con):
    q = lambda name: con.execute(EXERCISES[name]).fetchall()  # noqa: E731
    dups = q("ex2_dup_registrations")
    assert len(dups) == 5 and {n for _, n in dups} == {2}
    assert q("ex2_null_group") == [(20,)]
    # 3 月は 31 日に注文があるので BETWEEN だと落ちる。6 月は末日に注文が無く同じ件数になる
    assert q("ex4_march_half_open") == [(820,)] and q("ex4_march_between") == [(789,)]
    assert q("ex4_june_half_open") == [(155,)] == q("ex4_june_between")
    assert q("ex4_last_order") == [("2026-06-28 22:20:01",)]
    # 練習問題 1 と 3 の数字
    statuses = dict(rows(con, "group_status_lower"))
    assert sum(v for k, v in statuses.items() if k != "cancelled") == 2472
    assert 505 - scalar(con, "exists_cancelled") == 171
    assert q("ex3_never_cancelled") == [(171,)]


def test_customer_count_matches_python_data(con):
    # SQL の数え方が Python 側のデータと一致することの確認
    assert scalar(con, "count_variants") == len(shop.generate()["customers"])


def test_postgres_differs_from_duckdb(pg_dsn):
    """DuckDB が許す別名の WHERE と、整数の割り算は、PostgreSQL では挙動が違います。"""
    import psycopg
    from psycopg import errors

    with psycopg.connect(pg_dsn) as con:
        assert con.execute("SELECT 7 / 2").fetchone() == (3,)
        with pytest.raises(errors.UndefinedColumn, match='column "double_price" does not exist'):
            con.execute("SELECT price * 2 AS double_price FROM (VALUES (1)) AS t(price) WHERE double_price > 1")


def test_run_sql_script(tmp_path, monkeypatch, capsys):
    """読者が使う run_sql.py が最後まで動くこと。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["run_sql.py", str(HERE / "queries.sql"), "count_tokyo"])
    spec = importlib.util.spec_from_file_location("__main__", HERE / "run_sql.py")
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    assert "44" in capsys.readouterr().out
