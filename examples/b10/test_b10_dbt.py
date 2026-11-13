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
    shutil.copytree(HERE, proj, ignore=shutil.ignore_patterns("test_*.py", "__pycache__", "exercises", "target", "logs", "*.duckdb"))
    db = tmp_path / "neboske.duckdb"
    write_duckdb(db)
    return proj, db


def dbt(project, *args, check=True):
    proj, db = project
    env = {**os.environ, "DBT_DUCKDB_PATH": str(db), "DBT_SEND_ANONYMOUS_USAGE_STATS": "False"}
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
    assert "WARN" in result.stdout  # events.event_id の重複 (severity: warn)
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


def test_incremental_model_picks_up_new_and_late_changes(project):
    dbt(project, "build", "--exclude", "tag:known_issue")
    before = query(project, "select count(*), max(order_date) from analytics.fct_daily_sales")
    # 生データに、最後の日より後の注文と、直近の日の注文の状態変更を足す
    con = duckdb.connect(str(project[1]))
    last_day = str(con.execute("select max(order_date) from analytics.fct_daily_sales").fetchone()[0])
    assert con.execute("select count(*) from analytics.fct_daily_sales where order_date = ?", [last_day]).fetchone() == (1,)
    con.execute("insert into main.orders values (9001, 1, '2026-07-10 09:00:00', 'placed')")
    con.execute("insert into main.order_items values (9001, 1, 1, 2, 1000)")
    con.execute("update main.orders set status = 'cancelled' where ordered_at::date = ?::date "
                "and status <> 'cancelled'", [last_day])
    con.close()
    result = dbt(project, "build", "--select", "stg_orders+", "--exclude", "tag:known_issue")
    assert "fct_daily_sales" in result.stdout
    after = query(project, "select count(*), max(order_date) from analytics.fct_daily_sales")
    assert after[0][0] == before[0][0] + 1
    assert str(after[0][1]) == "2026-07-10"
    assert query(project, "select sales from analytics.fct_daily_sales where order_date = '2026-07-10'") == [(2000,)]
    # 直近の日はすべてキャンセルになったが、新しい結果にその日の行が無いので、古い行は消えずに残る
    stale = f"select count(*) from analytics.fct_daily_sales where order_date = '{last_day}'"
    assert query(project, stale) == [(1,)]
    # 全件作り直し (--full-refresh) では消える
    dbt(project, "build", "--select", "fct_daily_sales", "--full-refresh")
    assert query(project, stale) == [(0,)]
    # 日付が重複していない (delete+insert で作り直した日が二重にならない)
    assert query(project, "select count(*) - count(distinct order_date) from analytics.fct_daily_sales") == [(0,)]


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


def test_exercise_singular_test_passes(project):
    proj, _ = project
    shutil.copy(HERE / "exercises" / "assert_events_received_after_event_time.sql", proj / "tests")
    dbt(project, "build", "--select", "stg_events", "assert_events_received_after_event_time")
