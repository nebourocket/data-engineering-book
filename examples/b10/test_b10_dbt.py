"""dbt のプロジェクト (examples/b10) を一時フォルダにコピーして動かし、結果を確かめます。"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from neboske_shop import write_duckdb  # noqa: E402


@pytest.fixture
def project(tmp_path):
    """プロジェクトのコピーと、生データ入りの DuckDB ファイルを用意します。"""
    proj = tmp_path / "neboske_dbt"
    shutil.copytree(HERE, proj, ignore=shutil.ignore_patterns("test_*.py", "__pycache__", "exercises", "ci-example.yml", "target", "logs", "*.duckdb"))
    db = tmp_path / "neboske.duckdb"
    write_duckdb(db)
    return proj, db


def dbt(project, *args, check=True):
    proj, db = project
    env = {**os.environ, "DBT_DUCKDB_PATH": str(db), "DBT_SEND_ANONYMOUS_USAGE_STATS": "False", "DBT_CI_PATH": str(db)}
    result = subprocess.run(
        ["dbt", *args, "--profiles-dir", str(proj), "--project-dir", str(proj), "--no-use-colors"],
        capture_output=True, text=True, env=env)
    if check:
        assert result.returncode == 0, result.stdout[-3000:]
    return result


def query(project, sql):
    con = duckdb.connect(str(project[1]), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_build_passes_and_marts_are_right(project):
    result = dbt(project, "build", "--exclude", "tag:known_issue")
    print(result.stdout)
    assert "ERROR=0" in result.stdout
    assert "WARN 40 source_unique_raw_events_event_id" in result.stdout  # 二重に届いた 40 件 (severity: warn)
    # 注文 3,000 件が 1 件 1 行で入り、状態は小文字にそろっている
    assert query(project, "select count(*), count(distinct order_id) from analytics.fct_orders") == [(3000, 3000)]
    assert {r[0] for r in query(project, "select distinct status from analytics.fct_orders")} == {
        "placed", "shipped", "delivered", "cancelled"}
    # 二重に届いたイベント 40 件が取り除かれる
    assert query(project, "select count(*) from analytics.stg_events") == [(4000,)]
    assert query(project, "select count(*) from main.events") == [(4040,)]
    # 日別売上の合計は、キャンセルを除いた注文の合計に一致する
    assert query(project, "select sum(sales) from analytics.fct_daily_sales") == query(
        project, "select sum(order_amount) from analytics.fct_orders where status <> 'cancelled'")
    # ビューとテーブルの違い
    kinds = dict(query(project, "select table_name, table_type from information_schema.tables "
                                "where table_schema = 'analytics'"))
    assert kinds["stg_orders"] == "VIEW" and kinds["fct_orders"] == "BASE TABLE"


def test_failing_test_stops_the_build(project):
    result = dbt(project, "test", "--select", "tag:known_issue", check=False)
    print(result.stdout)
    assert result.returncode != 0
    assert "FAIL 5" in result.stdout
    # tag:known_issue を外した build は、このテストで止まる
    assert dbt(project, "build", check=False).returncode != 0


def _sales(project, day):
    return query(project, f"select orders, sales from analytics.fct_daily_sales where order_date = '{day}'")


def test_incremental_new_day_is_added(project):
    dbt(project, "build", "--exclude", "tag:known_issue")
    before = query(project, "select count(*) from analytics.fct_daily_sales")[0][0]
    con = duckdb.connect(str(project[1]))
    con.execute("insert into main.orders values (9001, 1, '2026-07-10 09:00:00', 'placed')")
    con.execute("insert into main.order_items values (9001, 1, 1, 2, 1000)")
    con.close()
    result = dbt(project, "build", "--select", "stg_orders+", "--exclude", "tag:known_issue")
    assert "fct_daily_sales" in result.stdout
    assert query(project, "select count(*) from analytics.fct_daily_sales")[0][0] == before + 1
    assert _sales(project, "2026-07-10") == [(1, 2000)]


def test_incremental_recomputes_days_inside_the_window_only(project):
    dbt(project, "build", "--exclude", "tag:known_issue")
    last = query(project, "select max(order_date) from analytics.fct_daily_sales")[0][0]
    # 窓の中 (最後の日から 7 日以内) で、キャンセルされていない注文が 2 件以上ある日の、1 件をキャンセルにする
    inside = query(project, f"""
        select order_date from analytics.fct_daily_sales
        where orders >= 2 and order_date >= date '{last}' - 7 and order_date < date '{last}' order by order_date limit 1""")[0][0]
    old = query(project, f"""
        select order_date from analytics.fct_daily_sales
        where orders >= 2 and order_date < date '{last}' - 7 order by order_date desc limit 1""")[0][0]
    cancelled = {}
    con = duckdb.connect(str(project[1]))
    for day in (inside, old):
        order_id, amount = con.execute(f"""
            select o.order_id, sum(i.quantity * i.unit_price) from main.orders o
            join main.order_items i using (order_id)
            where o.ordered_at::date = date '{day}' and lower(o.status) <> 'cancelled'
            group by o.order_id order by o.order_id limit 1""").fetchone()
        con.execute("update main.orders set status = 'cancelled' where order_id = ?", [order_id])
        cancelled[day] = amount
    con.close()
    orders_in, sales_in = _sales(project, inside)[0]
    orders_old, sales_old = _sales(project, old)[0]
    dbt(project, "build", "--select", "stg_orders+", "--exclude", "tag:known_issue")
    # 窓の中の日は、新しい売上に変わる。窓より古い日は、incremental では古いまま
    assert _sales(project, inside) == [(orders_in - 1, sales_in - cancelled[inside])]
    assert _sales(project, old) == [(orders_old, sales_old)]
    # 全件を作り直すと、古い日も反映される
    dbt(project, "build", "--select", "fct_daily_sales", "--full-refresh")
    assert _sales(project, old) == [(orders_old - 1, sales_old - cancelled[old])]


def test_incremental_keeps_a_stale_row_when_the_day_becomes_empty(project):
    dbt(project, "build", "--exclude", "tag:known_issue")
    last = str(query(project, "select max(order_date) from analytics.fct_daily_sales")[0][0])
    con = duckdb.connect(str(project[1]))  # 後の日の注文は足さず、最後の日の注文を全部キャンセルにする
    con.execute("update main.orders set status = 'cancelled' where ordered_at::date = ?::date", [last])
    con.close()
    dbt(project, "build", "--select", "stg_orders+", "--exclude", "tag:known_issue")
    stale = f"select count(*) from analytics.fct_daily_sales where order_date = '{last}'"
    assert query(project, stale) == [(1,)]  # 結果が 0 行の日は消す対象にならず、古い行が残る
    dbt(project, "build", "--select", "fct_daily_sales", "--full-refresh")
    assert query(project, stale) == [(0,)]  # 全件を作り直すと消える


def test_docs_generate_lists_lineage(project):
    dbt(project, "docs", "generate")
    import json

    manifest = json.loads((project[0] / "target" / "manifest.json").read_text(encoding="utf-8"))
    parents = manifest["parent_map"]["model.neboske.fct_orders"]
    assert sorted(parents) == ["model.neboske.int_order_totals", "model.neboske.stg_orders"]


def test_selection_with_plus_selects_descendants_only(project):
    result = dbt(project, "ls", "--select", "stg_orders+", "--resource-type", "model")
    lines = sorted(line.strip() for line in result.stdout.splitlines() if line.startswith("neboske."))
    assert lines == ["neboske.marts.fct_daily_sales", "neboske.marts.fct_orders", "neboske.staging.stg_orders"]


def test_removing_clean_text_makes_accepted_values_fail(project):
    proj, _ = project
    path = proj / "models" / "staging" / "stg_orders.sql"
    path.write_text(path.read_text(encoding="utf-8").replace("{{ clean_text('status') }}", "status"), encoding="utf-8")
    result = dbt(project, "build", "--select", "stg_orders", check=False)
    print(result.stdout)
    assert result.returncode != 0
    assert "FAIL 1 accepted_values_stg_orders_status" in result.stdout  # 違反した「値」が 1 種類 (SHIPPED)


def test_exercise_failing_singular_test_then_fixed(project):
    proj, _ = project
    shutil.copy(HERE / "exercises" / "assert_no_late_events.sql", proj / "tests")
    result = dbt(project, "build", "--select", "stg_events", "assert_no_late_events", check=False)
    print(result.stdout)
    assert result.returncode != 0 and "FAIL 121 assert_no_late_events" in result.stdout
    (proj / "tests" / "assert_no_late_events.sql").unlink()
    shutil.copy(HERE / "exercises" / "assert_no_late_events_fixed.sql", proj / "tests")
    dbt(project, "build", "--select", "stg_events", "assert_no_late_events_fixed")


def test_ci_target_parses(project):
    dbt(project, "parse", "--target", "ci")
