"""第 6 章の SQL を、ねぼすけ商店の DuckDB（と PostgreSQL）に流して結果を確かめます。"""
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


shop = _load("neboske_shop_b06", COMMON / "neboske_shop.py")
run_sql = _load("run_sql_b06", HERE.parent / "b05" / "run_sql.py")


def queries(name):
    return run_sql.split_queries((HERE / name).read_text(encoding="utf-8"))


def first_cell(con, sql):
    """EXPLAIN 系は 2 列目に計画の文字列が入っています。"""
    return con.execute(sql).fetchall()[0][-1]


def D(s):
    return str(s)


EXPECT = {
    "daily_sales_view": lambda r: True,
    "daily_sales_shape": lambda r: [(171, "2026-01-04", "2026-06-28")] == [(r[0][0], D(r[0][1]), D(r[0][2]))],
    "row_number_nth": lambda r: [x[3] for x in r] == [1, 2, 3] and [x[0] for x in r] == [1983, 1, 2085],
    "rank_compare": lambda r: [x[2:] for x in r] == [
        (1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, 4), (5, 5, 5), (6, 5, 5), (7, 7, 6), (8, 8, 7)],
    "lag_gap": lambda r: [x[3] for x in r] == [None, 23, 19] and r[0][2] is None,
    "running_total": lambda r: [x[2] for x in r] == [4900, 24300, 34650, 67700],
    "share_of_total": lambda r: [x[2] for x in r] == [25.8, 25.7, 22.7, 15.4, 10.3],
    "moving_avg_frames": lambda r: r[5][2:] == (29483.0, 34400.0, 5) and r[9][2:] == (51757.0, 54875.0, 6),
    "last_value_trap": lambda r: [x[2] for x in r] == [4900, 19400, 10350] and {x[3] for x in r} == {30000},
    "cte_top_customers": lambda r: r == [(442, 257400), (434, 187950), (226, 183000)],
    "recursive_dates": lambda r: len(r) == 7 and D(r[-1][0]) == "2026-01-07",
    "gap_fill": lambda r: len(r) == 9 and [x[1] for x in r[:4]] == [4900, 0, 0, 19400],
    "recursive_tree": lambda r: [(x[1], x[2]) for x in r] == [
        ("店長", 0), ("発送係長", 1), ("問い合わせ担当", 1), ("発送担当", 2)],
    "dup_events": lambda r: r == [(4040, 4000)],
    "dedup_events": lambda r: r == [(4000,)],
    "dedup_customers_qualify": lambda r: r == [(480,)],
    "latest_order_per_customer": lambda r: r == [(1, 1926, "2026-06-08 02:48:54"), (2, 1989, "2026-06-02 20:01:53"),
                                                 (3, 1213, "2026-06-24 11:32:03")],
    "latest_distinct_on": lambda r: [x[1] for x in r] == [1926, 1989, 1213],
    "latest_arg_max": lambda r: r == [(1, 1926), (2, 1989), (3, 1213)],
    "sessions_small": lambda r: [x[2] for x in r] == [1, 1, 1, 2, 2, 1],
    "sessions_events": lambda r: r == [(2930,)],
    "pivot_case": lambda r: r[0] == ("2026-01", 28, 64, 38, 33) and sum(sum(x[1:]) for x in r) == 3000,
    "pivot_duckdb": lambda r: r[0] == ("2026-01", 33, 38, 28, 64) and sum(sum(x[1:]) for x in r) == 3000,
    "explain_plan": lambda r: True,
    "explain_analyze": lambda r: True,
}

Q = queries("queries.sql")


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    path = tmp_path_factory.mktemp("b06") / "shop.duckdb"
    shop.write_duckdb(path)
    con = duckdb.connect(str(path))
    out = {name: con.execute(sql).fetchall() for name, sql in Q.items()}
    out["_con"] = con
    yield out
    con.close()


def test_every_query_has_an_expectation():
    assert set(Q) == set(EXPECT)


@pytest.mark.parametrize("name", sorted(Q))
def test_query(results, name):
    assert EXPECT[name](results[name]), results[name]


def test_pivot_forms_agree(results):
    case = {r[0]: r[1:] for r in results["pivot_case"]}
    duck = {r[0]: (r[3], r[4], r[2], r[1]) for r in results["pivot_duckdb"]}
    assert case == duck


def test_three_latest_forms_agree(results):
    a = [(r[0], r[1]) for r in results["latest_order_per_customer"]]
    assert a == [(r[0], r[1]) for r in results["latest_distinct_on"]]
    assert a == results["latest_arg_max"]


# 注意: EXPLAIN の見積もり行数（~600 など）と Row Groups の数（17）は DuckDB 2.0.0 に固定した値です。
# DuckDB を上げて失敗したら、本文の出力例もあわせて見直してください。
def test_explain_shows_filter_and_estimate_gap(results):
    con = results["_con"]
    plan = first_cell(con, Q["explain_plan"])
    assert "Hash Join" in plan and "Filters: ordered_at >= '2026-03-01'" in plan
    analyzed = first_cell(con, Q["explain_analyze"])
    assert "Total Time" in analyzed and "5,812 rows" in analyzed
    # 見積もり (~600) と実際 (2,340) は違う
    assert "~600 rows" in plan and "2,340 rows" in analyzed


def test_duckdb_index_scan():
    q = queries("duckdb_index.sql")
    con = duckdb.connect()
    con.execute(q["setup"])
    before = first_cell(con, q["scan_before"])
    assert "Sequential Scan" in before and "Row Groups Scanned: 17 / 17" in before
    con.execute(q["create_index"])
    after = first_cell(con, q["scan_after"])
    assert "Index Scan" in after and "Row Groups Scanned: 0 / 17" in after
    # EXPLAIN だけでは Seq Scan と出る。実際に使われたかは EXPLAIN ANALYZE で見る
    assert "Sequential Scan" in first_cell(con, q["plan_after"])
    # 並べて置いた表は、インデックスがなくても行グループを読み飛ばせる
    con.execute(q["sorted_setup"])
    assert "Row Groups Scanned: 1 / 17" in first_cell(con, q["sorted_scan"])
    cols = first_cell(con, q["columns_read"])
    assert "Projections: id" in cols and "h" not in cols.split("Projections: id")[1].split("\n")[0]


def test_postgres_index_changes_plan(pg_dsn):
    import psycopg

    q = queries("pg_index.sql")
    with psycopg.connect(pg_dsn, autocommit=True) as con:
        def plan(name):
            return "\n".join(r[0] for r in con.execute(q[name]).fetchall())

        con.execute(q["setup"])
        con.execute(q["analyze"])
        assert plan("plan_before").startswith("Seq Scan on big")
        con.execute(q["create_index"])
        assert plan("plan_after").startswith("Index Scan using big_id on big")
        # 行の大半を読む条件では、インデックスがあっても全件走査を選ぶ
        con.execute(q["create_index_grp"])
        assert plan("plan_low_selectivity").startswith("Seq Scan on big")
        # 約 0.1% の行を読む条件なら、grp のインデックスを使う
        assert "big_grp" in plan("plan_high_selectivity")


def test_exercises(results):
    ex = queries("exercises.sql")
    con = results["_con"]
    q = lambda name: con.execute(ex[name]).fetchall()  # noqa: E731
    top2 = q("ex1_top2_per_category")
    assert len(top2) == 10 and top2[0] == ("寝具", "布団カバー(大)", 5000)
    assert q("ex2_avg_gap") == [(2496, 12.0)]
    assert q("ex3_second_order") == [(498,)]
    by_type = dict(q("ex4_dedup_by_type"))
    assert by_type == {"view": 1991, "purchase": 677, "add_to_cart": 674, "search": 658}
    assert sum(by_type.values()) == 4000
    # 注文のある顧客 504 人 - 注文 1 回だけの 6 人 = 498 人
    assert con.execute("SELECT count(*) FROM (SELECT customer_id FROM orders GROUP BY 1 HAVING count(*) >= 2)").fetchone() == (498,)


run_index = _load("run_index_b06", HERE / "run_index.py")


def test_run_index_duckdb():
    out = run_index.run_duckdb(HERE / "duckdb_index.sql")
    assert "Index Scan" in out["scan_after"] and "Index Scan" not in out["scan_before"]


def test_run_index_postgres(pg_dsn):
    out = run_index.run_postgres(HERE / "pg_index.sql", pg_dsn)
    assert out["plan_before"].startswith("Seq Scan") and out["plan_after"].startswith("Index Scan")


def test_usage_runs_named_queries(tmp_path, monkeypatch, capsys):
    """usage.sh と同じ引数で、ビューを作ってから使うクエリを流せること。"""
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("__main__", HERE.parent / "b05" / "run_sql.py")
    monkeypatch.setattr("sys.argv", ["run_sql.py", str(HERE / "queries.sql"), "daily_sales_view", "moving_avg_frames"])
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    assert "avg_range" in capsys.readouterr().out
