"""第16章のコードを動かして、本文の数字と主張（逆 ETL の冪等性・定義のずれ・渡し方）を確かめます。"""
import csv
import sqlite3
import sys
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import file_exchange  # noqa: E402
import reverse_etl  # noqa: E402
import sales_metrics  # noqa: E402
import serving_tables  # noqa: E402
import shop_warehouse  # noqa: E402


@pytest.fixture(scope="module")
def warehouse_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("b16") / "warehouse.duckdb"
    shop_warehouse.build_warehouse(path)
    return path


@pytest.fixture
def warehouse(warehouse_path, tmp_path):
    """テストごとにコピーを開きます (集計の基準日を変えるテストがあるため)。"""
    copy = tmp_path / "w.duckdb"
    copy.write_bytes(warehouse_path.read_bytes())
    con = duckdb.connect(str(copy))
    yield con
    con.close()


@pytest.fixture
def crm():
    con = sqlite3.connect(":memory:")
    yield con
    con.close()


def test_summary_counts(warehouse):
    assert warehouse.execute("select count(*) from customer_summary").fetchone()[0] == 505
    segments = dict(warehouse.execute("select segment, count(*) from customer_summary group by 1").fetchall())
    assert segments == {"active": 237, "dormant": 267, "never": 1}
    # 同じメールで別の customer_id の重複登録 (第13章の欠陥 2) が 5 組ある
    dup = warehouse.execute(
        "select count(*) from (select email from customer_summary where email is not null group by 1 having count(*) > 1)"
    ).fetchone()[0]
    assert dup == 5


def test_definitions_disagree_by_month(warehouse):
    rows = {r[0]: r[1:] for r in sales_metrics.monthly_by_definition(warehouse)}
    assert rows["2026-03"] == (11877250, 9878150, 3888200)
    for all_orders, not_cancelled, delivered in rows.values():
        assert all_orders > not_cancelled > delivered


def test_metric_layer_matches_the_dbt_rule(warehouse):
    """第10章の fct_daily_sales (キャンセル除く) と同じ値が、指標の定義から出る。"""
    by_month = dict(warehouse.execute(sales_metrics.metric_sql("sales", "month")).fetchall())
    assert by_month["2026-03"] == 9878150
    daily = warehouse.execute(sales_metrics.metric_sql("sales", "day")).fetchall()
    assert sum(v for d, v in daily if str(d).startswith("2026-03")) == 9878150
    assert warehouse.execute(sales_metrics.metric_sql("orders", "month")).fetchall()[2] == ("2026-03", 680)


def test_unknown_metric_fails_fast():
    with pytest.raises(KeyError):
        sales_metrics.metric_sql("profit", "month")


def test_first_sync_inserts_and_second_changes_nothing(warehouse, crm):
    first = reverse_etl.sync_contacts(warehouse, crm, "2026-06-30")
    assert first == {"read": 485, "inserted": 485, "updated": 0, "unchanged": 0, "skipped": 20}
    # 実行日 (changed_at) が違っても、中身が同じなら何も書かない
    second = reverse_etl.sync_contacts(warehouse, crm, "2026-07-01")
    assert second == {"read": 485, "inserted": 0, "updated": 0, "unchanged": 485, "skipped": 20}
    assert crm.execute("select count(*), min(changed_at), max(changed_at) from contacts").fetchone() == (485, "2026-06-30", "2026-06-30")


def test_only_changed_rows_are_updated(warehouse, crm):
    reverse_etl.sync_contacts(warehouse, crm, shop_warehouse.AS_OF)
    shop_warehouse.refresh_summary(warehouse, serving_tables.LATER)
    third = reverse_etl.sync_contacts(warehouse, crm, serving_tables.LATER)
    assert third == {"read": 485, "inserted": 0, "updated": 76, "unchanged": 409, "skipped": 20}
    # 更新された行だけが changed_at を持ち替え、segment は active から dormant に動いた
    assert crm.execute("select count(*) from contacts where changed_at = ?", [serving_tables.LATER]).fetchone()[0] == 76
    assert crm.execute("select count(*) from contacts where segment = 'active'").fetchone()[0] == 233 - 76


def test_upsert_keeps_columns_owned_by_the_crm(warehouse, crm):
    reverse_etl.sync_contacts(warehouse, crm, shop_warehouse.AS_OF)
    crm.execute("update contacts set owner = '佐藤' where customer_id = 1")
    crm.commit()
    shop_warehouse.refresh_summary(warehouse, serving_tables.LATER)
    reverse_etl.sync_contacts(warehouse, crm, serving_tables.LATER)
    assert crm.execute("select owner from contacts where customer_id = 1").fetchone()[0] == "佐藤"


def test_insert_or_replace_wipes_the_owner(warehouse, crm):
    rows, _ = reverse_etl.read_source(warehouse)
    reverse_etl.apply_upsert(crm, rows, "2026-06-30")
    crm.execute("update contacts set owner = '佐藤' where customer_id = 1")
    crm.commit()
    crm.executemany(reverse_etl.REPLACE_SQL, [(*r, "2026-06-30") for r in rows])
    assert crm.execute("select owner from contacts where customer_id = 1").fetchone()[0] is None


def test_plain_insert_duplicates_or_fails(warehouse, crm):
    rows, _ = reverse_etl.read_source(warehouse)
    # 主キーの無い表への追記は、2 回で倍になる
    crm.execute(reverse_etl.NAIVE_DDL)
    for _ in range(2):
        crm.executemany(reverse_etl.NAIVE_INSERT_SQL, [(*r, "2026-06-30") for r in rows])
    assert crm.execute("select count(*) from contacts_naive").fetchone()[0] == 970
    # 主キーのある表への追記は、2 回目に止まる
    reverse_etl.apply_upsert(crm, rows, "2026-06-30")
    with pytest.raises(sqlite3.IntegrityError):
        crm.executemany(reverse_etl.NAIVE_INSERT_SQL.replace("contacts_naive", "contacts"), [(*r, "x") for r in rows])


def test_failure_in_the_middle_rolls_everything_back(warehouse, crm):
    rows, _ = reverse_etl.read_source(warehouse)
    broken = rows[:10] + [(9999, "x@example.com", "active", None)] + rows[10:]
    with pytest.raises(sqlite3.IntegrityError):
        reverse_etl.apply_upsert(crm, broken, "2026-06-30")
    assert crm.execute("select count(*) from contacts").fetchone()[0] == 0


def test_export_has_no_personal_columns_and_a_bom(warehouse, tmp_path):
    path = tmp_path / "customers.csv"
    assert file_exchange.export_csv(warehouse, path) == 505
    assert path.read_bytes().startswith(b"\xef\xbb\xbfcustomer_id")
    rows = file_exchange.read_export(path)
    assert len(rows) == 505
    assert set(rows[0]) == {"customer_id", "orders", "lifetime_spend", "last_order_date", "segment"}
    assert not list(tmp_path.glob("*.tmp"))


def test_tampered_export_is_refused(warehouse, tmp_path):
    path = tmp_path / "customers.csv"
    file_exchange.export_csv(warehouse, path)
    path.write_bytes(path.read_bytes() + b"1,1,1,2026-01-01,active\n")
    with pytest.raises(ValueError):
        file_exchange.read_export(path)


def test_read_only_connection_cannot_write(warehouse_path, tmp_path, monkeypatch):
    copy = tmp_path / "w.duckdb"
    copy.write_bytes(warehouse_path.read_bytes())
    file_exchange.publish_view(copy)
    monkeypatch.setenv("WAREHOUSE_PATH", str(copy))
    con = file_exchange.connect_for_notebook()
    try:
        assert con.execute("select count(*) from serving_customers").fetchone()[0] == 505
        with pytest.raises(duckdb.Error, match="read-only"):
            con.execute("delete from customer_summary")
        with pytest.raises(duckdb.Error):
            con.execute("select email from serving_customers")
    finally:
        con.close()


def test_notebook_needs_the_environment_variable(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_PATH", raising=False)
    with pytest.raises(RuntimeError):
        file_exchange.connect_for_notebook()


def test_tables_are_up_to_date():
    for name, (header, rows) in serving_tables.tables().items():
        with (HERE.parents[1] / "data" / "tables" / f"{name}.csv").open(encoding="utf-8", newline="") as f:
            assert list(csv.reader(f)) == [header] + [[str(c) for c in r] for r in rows], name


def test_exercise_answers(warehouse, crm):
    rows = {r[0]: r[1:] for r in sales_metrics.monthly_by_definition(warehouse)}
    assert rows["2026-03"][0] - rows["2026-03"][1] == 1999100
    # 練習: where を消した upsert は、同じ日の 2 回目でも全行を更新する
    no_guard = reverse_etl.UPSERT_SQL.split("where contacts.email")[0]
    rows_src, _ = reverse_etl.read_source(warehouse)
    reverse_etl.apply_upsert(crm, rows_src, "2026-06-30")
    before = crm.total_changes
    with crm:
        crm.executemany(no_guard, [(*r, "2026-07-01") for r in rows_src])
    assert crm.total_changes - before == 485
    # 練習: 指標を 1 つ足す
    metrics = {**sales_metrics.METRICS, "aov": "sum(order_amount) filter (where status <> 'cancelled') / count(*) filter (where status <> 'cancelled')"}
    sales_metrics.METRICS["aov"] = metrics["aov"]
    try:
        assert round(warehouse.execute(sales_metrics.metric_sql("aov", "month")).fetchall()[2][1], 2) == 14526.69
    finally:
        del sales_metrics.METRICS["aov"]
