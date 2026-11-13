"""第 11 章のコードを動かして、本文の主張（プルーニング・並べ方・部分集計・マテビュー）を確かめます。"""
import importlib.util
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_b11", HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


demo = _load("partition_demo")
QUERIES = demo.split_queries((HERE / "queries.sql").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    root = tmp_path_factory.mktemp("b11") / "sales"
    demo.write_partitioned(root, demo.sales_lines())
    return root


def test_hive_layout(root):
    names = sorted(p.name for p in root.iterdir())
    assert names == [f"month=2026-0{m}" for m in range(1, 7)]
    assert all((root / n / "data_0.parquet").exists() for n in names)


def test_partition_filter_opens_one_file(root):
    stats = {r["name"]: r for r in demo.run_scenarios(root)}
    assert stats["full_scan"]["files_read"] == 6
    assert stats["month_filter"]["files_read"] == 1
    # パーティション列を使わない条件では、6 ファイルすべてを開く
    assert stats["date_filter_only"]["files_read"] == 6
    # 条件なしの 1/3 より少ない（3 月は全体の約 3 割）
    assert stats["month_filter"]["bytes_read"] < stats["full_scan"]["bytes_read"] / 3
    # SELECT * は列を絞ったときより多く読む
    assert stats["select_star"]["bytes_read"] > 3 * stats["month_filter"]["bytes_read"]
    # パーティション列を使わないと、条件を使ったときより多く読む
    assert stats["date_filter_only"]["bytes_read"] > 3 * stats["month_filter"]["bytes_read"]


def test_explain_shows_pruning(root):
    con = demo.open_sales(root)
    plan = con.execute(QUERIES["explain_month"]).fetchall()[0][1]
    assert "Scanning Files: 1/6" in plan and "Total Files Read: 1" in plan


def test_row_groups_skipped_by_zone_maps_without_partition_filter(root):
    con = demo.open_sales(root)
    plan = con.execute(QUERIES["explain_date_filter"]).fetchall()[0][1]
    assert "Total Files Read: 6" in plan and "Row Groups Scanned: 1 / 6" in plan


def test_exercise_queries(root):
    con = demo.open_sales(root)
    assert con.execute(QUERIES["ex_two_months"]).fetchone() == (258_292_600 + 155_564_450,)
    assert demo.scan_stats(con, QUERIES["ex_two_months"])["files_read"] == 2
    with_month = demo.scan_stats(con, QUERIES["ex_one_day_with_month"])
    only_day = demo.scan_stats(con, QUERIES["ex_one_day_only"])
    assert with_month["files_read"] == 1 and only_day["files_read"] == 6
    assert only_day["bytes_read"] > 1.2 * with_month["bytes_read"]
    a = con.execute(QUERIES["ex_one_day_with_month"]).fetchone()
    assert a == con.execute(QUERIES["ex_one_day_only"]).fetchone()


def test_same_answer_with_and_without_partition_filter(root):
    con = demo.open_sales(root)
    a = con.execute(QUERIES["month_filter"]).fetchone()
    b = con.execute(QUERIES["date_filter_only"]).fetchone()
    assert a == b == (268_815_700,)


def test_partial_aggregates(root):
    con = demo.open_sales(root)
    partial = con.execute(QUERIES["monthly_partial"]).fetchall()
    assert [r[2] for r in partial] == [8788, 23378, 43339, 41852, 25172, 7639]
    direct = con.execute(QUERIES["direct_total"]).fetchone()
    revenue, avg_line, avg_of_avgs = con.execute(QUERIES["combine_partials"]).fetchone()
    assert revenue == direct[0] == 928_950_600
    assert avg_line == pytest.approx(direct[1])
    # 平均の平均は、全体の平均と一致しない
    assert avg_of_avgs != pytest.approx(direct[1], abs=1e-6)


def test_clustering_skips_row_groups(tmp_path):
    cl = _load("clustering_demo")
    paths = cl.write_both(tmp_path)
    shuffled = cl.row_groups_scanned(paths["ばらばら"])
    ordered = cl.row_groups_scanned(paths["customer_id 順"])
    assert shuffled["scanned"] == shuffled["total"] == 15
    assert ordered["scanned"] == 1 and ordered["total"] == 15
    assert ordered["bytes_read"] < shuffled["bytes_read"] / 5
    # 並べた列（customer_id）以外の列で絞っても、読み飛ばせない
    other = cl.row_groups_scanned(paths["customer_id 順"], column="product_id", value=7)
    assert other["scanned"] == other["total"] == 15
    con = duckdb.connect()
    counts = [con.execute(cl.QUERY.format(path=p, column='customer_id', value=42)).fetchone() for p in paths.values()]
    assert counts[0] == counts[1]  # 並べ方を変えても答えは同じ


def test_materialized_view_is_a_snapshot(pg_dsn):
    import psycopg

    rows = demo.sales_lines(seeds=range(1, 4))
    queries = demo.split_queries((HERE / "matview.sql").read_text(encoding="utf-8"))
    with psycopg.connect(pg_dsn, autocommit=True) as con:
        con.execute("DROP SCHEMA IF EXISTS b11 CASCADE")
        con.execute("DROP ROLE IF EXISTS b11_analyst")
        try:
            con.execute("CREATE SCHEMA b11")
            con.execute("CREATE TABLE b11.sales_lines "
                        "(order_id int, ordered_at timestamp, quantity int, unit_price int)")
            with con.cursor() as cur:
                cur.executemany(
                    "INSERT INTO b11.sales_lines VALUES (%s, %s, %s, %s)",
                    [(r["order_id"], r["ordered_at"], r["quantity"], r["unit_price"]) for r in rows])
            con.execute(queries["create_mv"])
            total = lambda: con.execute("SELECT sum(revenue) FROM b11.daily_revenue").fetchone()[0]  # noqa: E731
            before = total()
            assert before == sum(r["quantity"] * r["unit_price"] for r in rows)
            con.execute("INSERT INTO b11.sales_lines VALUES (999999, '2026-03-01 10:00:00', 1, 1000)")
            assert total() == before  # 元の表が変わっても、更新するまで見える値は古いまま
            con.execute(queries["refresh_mv"])
            assert total() == before + 1000
            con.execute(queries["grant_mv"])
            con.execute("SET ROLE b11_analyst")
            assert total() == before + 1000
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                con.execute("SELECT count(*) FROM b11.sales_lines")
            con.execute("RESET ROLE")
        finally:
            con.execute("RESET ROLE")
            con.execute("DROP SCHEMA IF EXISTS b11 CASCADE")
            con.execute("DROP ROLE IF EXISTS b11_analyst")
