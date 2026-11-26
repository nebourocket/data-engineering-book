"""第1章のコードの検査。計画の形と、設定を変えたときの相対的な効果だけを確かめます (秒数の絶対値は見ません)。"""
import sys
from pathlib import Path

import pytest
from pyspark.sql import functions as F

sys.path.insert(0, str(Path(__file__).parent))
import demo  # noqa: E402
from demo import NO_AQE  # noqa: E402
from shopgen import make_events, make_products  # noqa: E402
from sparkstat import conf, measure  # noqa: E402


@pytest.fixture(scope="module")
def events(spark):
    return make_events(spark, 200_000).cache()


@pytest.fixture(scope="module")
def products(spark):
    return make_products(spark)


@pytest.fixture(autouse=True)
def plain_plans(spark):
    """計画を読みやすくするため、この章のテストでは AQE を切ります (第2章で入れます)。"""
    with conf(spark, NO_AQE):
        yield


def test_generator_is_deterministic_and_sized(spark):
    a = make_events(spark, 1_000).collect()
    b = make_events(spark, 1_000).collect()
    assert a == b and len(a) == 1_000
    assert {r.event_type for r in a} == {"view", "cart", "purchase"}


def test_transformations_are_lazy(spark, events):
    before, after = demo.lazy_demo(spark, events)
    assert before == 0 and after == 1


def test_partitions_split_the_rows(events):
    sizes = demo.rows_per_partition(events)
    assert len(sizes) == 4 and sum(sizes) == 200_000


def test_narrow_has_no_exchange_wide_has_one(events):
    narrow_exchanges, wide_kinds = demo.narrow_and_wide(events)
    assert narrow_exchanges == 0
    assert wide_kinds == ["hashpartitioning"]


def test_partial_aggregation_shrinks_shuffle(spark, events):
    rows = demo.shuffle_rows(spark, events)
    partitions, pairs = demo.partial_pairs(events)
    assert rows["event_type"] == pairs <= partitions * 3
    assert rows["user_id"] > 1_000 * rows["event_type"]


def test_exchange_kind_depends_on_operation(events):
    assert demo.exchange_kinds_by_operation(events) == {
        "groupBy": ["hashpartitioning"],
        "orderBy": ["rangepartitioning"],
        "repartition": ["RoundRobinPartitioning"],
        "count": ["SinglePartition"],
    }


def test_shuffle_partitions_sets_reduce_tasks(spark, events):
    out = demo.shuffle_partition_effect(spark, events, [1, 4, 200])
    assert [out[n][0] for n in (1, 4, 200)] == [1, 4, 200]
    assert out[200][1] >= 197 and out[1][1] == 0
    assert out[200][2] > out[1][2]  # 行数は同じ 12 行でも、小さな塊が増えて書き出しは大きくなる


def test_topology_and_stages(spark, events):
    assert demo.topology(spark) == {"master": "local[2]", "parallelism": 4}
    stages = demo.stages_of_groupby(spark, events)
    assert [s[1] for s in stages] == [4, 4]  # 手前のステージは入力の 4 分割、後ろは shuffle.partitions
    assert stages[0][2] == stages[1][3] > 0  # 書いた量と読んだ量が一致する


def test_small_files_are_packed_by_bytes_and_cores(spark, tmp_path):
    out = demo.input_partitions(spark, str(tmp_path), [1, 8, 100])
    assert out[1] == 1 and out[8] <= 4 and out[100] <= 4


def test_broadcast_threshold_switches_join(spark, events, products):
    out = demo.join_strategies(spark, events, products)
    assert out["default"] == {"broadcast": True, "sortmerge": False, "exchanges": 0}
    assert out["off"] == {"broadcast": False, "sortmerge": True, "exchanges": 2}


def test_sql_and_dataframe_share_one_plan(spark, events):
    assert demo.sql_and_dataframe_plans(spark, events)


def test_formatted_plan_has_numbered_operators(spark, tmp_path):
    demo.write_events(spark, str(tmp_path / "e"), 20_000)
    demo.write_products(spark, str(tmp_path / "p"))
    job = demo.report_job(spark.read.parquet(str(tmp_path / "e")), spark.read.parquet(str(tmp_path / "p")))
    text = demo.plan_text(job, "formatted")
    assert "Scan parquet" in text and "BroadcastHashJoin" in text
    assert "PushedFilters: [IsNotNull(event_type), EqualTo(event_type,purchase)" in text
    assert text.count("HashAggregate") >= 4  # 木に 2 回、詳細に 2 回


def test_case_study_each_fix_reduces_shuffle(spark, tmp_path):
    demo.write_events(spark, str(tmp_path / "e"), 400_000)
    demo.write_products(spark, str(tmp_path / "p"))
    a, b, c = demo.case_study(spark, str(tmp_path / "e"), str(tmp_path / "p"), repeat=1)
    assert (a["join"], b["join"], c["join"]) == ("SortMergeJoin", "BroadcastHashJoin", "BroadcastHashJoin")
    assert (a["exchanges"], b["exchanges"], c["exchanges"]) == (3, 1, 1)
    assert a["shuffle_write_mb"] > 10 * b["shuffle_write_mb"] > 0
    assert a["tasks"] > b["tasks"] > c["tasks"]


def test_exercise_exchange_counts(spark, events, products):
    narrow = events.filter("event_type = 'purchase'").select("user_id", "amount")
    with conf(spark, {"spark.sql.autoBroadcastJoinThreshold": "-1"}):
        big_join = events.join(products, "product_id")
        counts = (len(demo.exchange_kinds(narrow)), len(demo.exchange_kinds(narrow.distinct())),
                  len(demo.exchange_kinds(big_join)))
    assert counts == (0, 1, 2)


def test_exercise_global_count_has_two_stages(spark, events):
    _, stats = measure(spark, events.agg(F.count("*")).collect)
    assert [s["tasks"] for s in stats] == [4, 1]


def test_exercise_filter_is_pushed_below_join(spark, events, products):
    late = events.join(products, "product_id").filter(F.col("event_type") == "purchase")
    early = events.filter(F.col("event_type") == "purchase").join(products, "product_id")
    assert demo.normalize(demo.plan_text(late)) == demo.normalize(demo.plan_text(early))
