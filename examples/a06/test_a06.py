"""第6章のコードの検査。行数・書き換えた行数・答えの一致を確かめます (秒数は見ません)。"""
from pathlib import Path

import pytest

import aggregates
import model_case_study as case_study
import conformed
import datavault
import grain
import late_dim
import migrate
import mini_dim
import models
import semantic

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def shop():
    con = models.load_source(1)
    models.build_star(con)
    models.build_obt(con)
    datavault.create_vault(con)
    datavault.load_all(con)
    con.execute(datavault.CURRENT_VIEWS)
    return con


def test_three_models_give_the_same_answer(shop):
    star = shop.execute(models.REVENUE_STAR).fetchall()
    assert len(star) == 298
    assert star == shop.execute(models.REVENUE_OBT).fetchall() == shop.execute(datavault.REVENUE_VAULT).fetchall()


def test_vault_load_is_idempotent_and_order_independent(shop):
    tables = ["hub_order", "link_order_line", "sat_order_line", "sat_customer"]
    first = datavault.digest(shop, tables)
    datavault.load_all(shop)  # 2 回目: 何も増えない
    assert datavault.digest(shop, tables) == first
    other = models.load_source(1)
    datavault.create_vault(other)
    order = datavault.load_all(other, seed=5)
    assert order != list(datavault.HUB_LINK_LOADS) + list(datavault.SAT_LOADS)  # 本当に入れ替わった
    assert datavault.digest(other, tables) == first


def test_satellite_adds_a_row_only_when_hashdiff_changes():
    con = models.load_source(1)
    datavault.create_vault(con)
    datavault.load_all(con)
    con.execute("UPDATE customers SET prefecture = '沖縄' WHERE customer_id = 100")
    before = con.execute("SELECT count(*) FROM sat_customer").fetchone()[0]
    datavault.load_satellite(con, "sat_customer", "2026-07-01 00:00:00")
    assert con.execute("SELECT count(*) FROM sat_customer").fetchone()[0] == before + 1


def test_grain_trap(shop):
    result = grain.shipping_by_method(shop)
    right = result["orders (正しい)"]
    assert result["obt の単純な合計"] > right
    assert result["obt を注文で重複排除"] == right == result["obt の先頭明細だけ"]
    assert result["obt の SUM(DISTINCT)"] == 1500  # 400+500+600 の 3 種類しか足されない
    aov = grain.average_order_value(shop)
    assert aov["明細の平均"] < aov["注文の平均"]


def test_late_arriving_dimension():
    out = late_dim.demo()
    assert out["before_fix"]["inner_join_lines"] < out["before_fix"]["lines"]
    assert out["after_inferred"]["inner_join_lines"] == out["before_fix"]["lines"]
    assert out["after_inferred"]["unknown_lines_and_revenue"][0] > 0
    assert out["after_arrival"]["unknown_lines_and_revenue"] == (0, 0)
    assert out["inferred_members_added"] == out["rows_filled_on_arrival"] == 25


def test_mini_dimension_shrinks_history():
    r = mini_dim.simulate(n_customers=2000)
    assert r["mini_dimension_rows"] == 12
    assert r["scd2_rows_stable_only"] * 3 < r["scd2_rows_all_attributes"]


def test_migration_switches_only_when_reconciled():
    ok = migrate.migrate(models.load_source(1))
    assert ok == {"diff": {"only_in_old": 0, "only_in_new": 0}, "switched": True}
    bad = migrate.migrate(models.load_source(1), migrate.SALES_V2_BUGGY)
    assert bad["switched"] is False and bad["diff"]["only_in_old"] > 0


def test_departments_disagree_and_metric_definitions_fix_it(shop):
    hand = {k: shop.execute(v).fetchone()[0] for k, v in semantic.HAND_WRITTEN.items()}
    assert len(set(hand.values())) == 3
    march = "substr(o.ordered_at, 1, 7) = '2026-03'"
    for dept, metric in [("経理", "net_sales"), ("マーケティング", "gross_sales"), ("物流", "shipped_sales")]:
        assert shop.execute(semantic.compile_metric(metric, (), march)).fetchone()[0] == hand[dept]


def test_semantic_layer_refuses_wrong_grain():
    with pytest.raises(ValueError, match="category"):
        semantic.compile_metric("shipping_revenue", ["category"])


def test_ratio_metric_matches_direct_computation(shop):
    got = shop.execute(semantic.compile_metric("avg_order_value")).fetchone()[0]
    want = shop.execute("SELECT sum(amount) / count(DISTINCT order_id) FROM obt_sales WHERE status <> 'cancelled'"
                        ).fetchone()[0]
    assert got == pytest.approx(want)


def test_semantic_models_yaml_parses():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load((Path(__file__).parent / "semantic_models.yml").read_text(encoding="utf-8"))
    assert doc["semantic_models"][0]["measures"][0]["name"] == "line_amount"
    assert doc["metrics"][0]["type_params"]["measure"] == "line_amount"
    latest = yaml.safe_load((Path(__file__).parent / "semantic_models_latest.yml").read_text(encoding="utf-8"))
    assert latest["models"][0]["semantic_model"]["enabled"] is True
    assert latest["models"][0]["metrics"][0]["agg"] == "sum"


@pytest.mark.parametrize("scale", [1, 10])
def test_case_study_counts(scale):
    r = case_study.measure(scale)
    assert r["same_answer"] and r["rows"]["obt"] == 7469 * scale
    assert r["rows"]["vault"] > 3 * r["rows"]["obt"]
    assert r["scanned_bytes"]["obt"] < r["stored_bytes"]["obt"]  # 列指向: 必要な列だけ読めば済む
    changes = case_study.measure_changes(scale)
    assert changes["move_one_customer"]["star"]["rows"] == changes["move_one_customer"]["vault"]["rows"] == 1
    assert changes["move_one_customer"]["obt"]["rows"] == changes["lines_of_that_customer"] == 10
    assert changes["rename_category"]["obt"]["rows"] == 1740 * scale
    assert changes["rename_category"]["star"]["rows"] == changes["rename_category"]["vault"]["rows"] == 12
    assert changes["add_attribute"]["obt"]["rows"] == 7469 * scale


def test_case_rows_csv_is_what_the_code_produces():
    text = (ROOT / "data" / "tables" / "a06-case-rows.csv").read_text(encoding="utf-8")
    assert text == case_study.rows_csv((1, 10, 100))


def test_vault_handles_late_customers_without_losing_lines():
    r = late_dim.vault_demo()
    assert r["before_arrival"] == {"lines": 7469, "unknown_lines": 353, "hub_customer": 505, "sat_customer": 480}
    assert r["after_arrival"] == {"lines": 7469, "unknown_lines": 0, "hub_customer": 505, "sat_customer": 505}


def test_binary_and_pit_variants_give_the_same_answer_and_are_smaller():
    r = case_study.measure_vault_flavors(1)
    assert r["same_answer"]
    assert r["binary"]["stored_bytes"] < r["varchar"]["stored_bytes"]
    assert r["binary_pit"]["scanned_bytes"] < r["varchar"]["scanned_bytes"]


def test_star_scd2_move_touches_two_rows_and_vault_view_gains_a_join():
    assert case_study.star_scd2_move(1)["rows_touched"] == 2
    assert case_study.vault_view_joins() == {"joins_before": 7, "joins_after": 8}


def test_hash_key_collides_when_delimiter_is_in_the_business_key(shop):
    assert datavault.hash_collision_example(shop) is True


def test_conformed_dimension_allows_drill_across_but_team_b_spelling_does_not():
    r = conformed.non_conformed_demo()
    assert r["prefectures_matched_with_shared_dimension"] == r["prefectures"] == 10
    assert r["prefectures_matched_with_team_b_spelling"] == 1  # 綴りが同じなのは「北海道」だけ
    assert "has 4 columns but 5 values" in conformed.adding_a_column_breaks_select_star()


def test_aggregate_and_clustering_reduce_what_is_read():
    con = models.load_source(10)
    models.build_star(con)
    models.build_obt(con)
    con.execute(aggregates.AGG_SQL)
    agg = aggregates.aggregate_scan(con)
    assert agg["same_answer"] and agg["rows"]["agg_sales_month"] == 298
    assert agg["scanned_bytes"]["aggregate"] * 20 < agg["scanned_bytes"]["obt"]
    pc = aggregates.partition_and_cluster(con, row_group_size=5000)
    assert pc["files_read_for_one_month"] == 1 < pc["partition_files"]
    assert pc["clustered"]["row_groups_that_may_contain_tokyo"] < pc["unsorted"]["row_groups_that_may_contain_tokyo"]


def test_profile_key_adds_a_column_but_no_rows():
    con = models.load_source(1)
    models.build_star(con)
    r = mini_dim.profile_key_cost(con)
    assert r["rows"] == r["rows_after"] and r["bytes_after"] > r["bytes_before"]


def test_pit_form_keeps_lines_of_late_customers():
    con = models.load_source(1)
    con.execute("DELETE FROM customers WHERE customer_id % 20 = 0")
    datavault.create_vault(con)
    datavault.load_all(con)
    con.execute(datavault.CURRENT_VIEWS)
    con.execute(datavault.PIT_SQL)
    assert con.execute(datavault.REVENUE_PIT).fetchall() == con.execute(datavault.REVENUE_VAULT).fetchall()
    total = con.execute("SELECT sum(revenue) FROM (" + datavault.REVENUE_PIT + ")").fetchone()[0]
    full = con.execute("SELECT sum(amount) FROM v_sales WHERE status <> 'cancelled'").fetchone()[0]
    assert total == full
