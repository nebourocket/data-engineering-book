"""第2章のコードの検査。計画の形・タスク数・ファイル数・相対的な効果だけを確かめます (秒数の絶対値は見ません)。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import tuning  # noqa: E402
from tuning import F, make_events, make_skewed_events, make_users  # noqa: E402


@pytest.fixture(scope="module")
def events(spark):
    return make_events(spark, 200_000).cache()


@pytest.fixture(scope="module")
def skewed(spark):
    return make_skewed_events(spark, 1_000_000).cache()


@pytest.fixture(scope="module")
def users(spark):
    return make_users(spark)


def test_aqe_coalesces_empty_shuffle_partitions(spark, events):
    out = tuning.aqe_coalesce(spark, events)
    assert out["off"] == (200, False)
    assert out["on"][0] < 200 and out["on"][1] is True


def test_aqe_switches_join_at_runtime(spark, events, users, tmp_path):
    users.coalesce(1).write.parquet(str(tmp_path / "u"))
    assert tuning.aqe_join_switch(spark, events, str(tmp_path / "u")) == (True, True)


def test_salting_toy_splits_the_big_key(spark):
    before, after = tuning.salting_toy(spark)
    assert before["math"] == 5 and after["math#0"] + after["math#1"] == 5 and max(after.values()) == 3


def test_salting_table_matches_the_csv_in_the_book(spark, tmp_path):
    tuning.write_salting_table(spark, str(tmp_path / "t.csv"))
    book = Path(__file__).parent.parent.parent / "data" / "tables" / "a02-salting-toy.csv"
    assert (tmp_path / "t.csv").read_text(encoding="utf-8") == book.read_text(encoding="utf-8")


def test_broadcast_estimate_comes_from_the_parquet_file(spark, events, users, tmp_path):
    users.coalesce(1).write.parquet(str(tmp_path / "u"))
    out = tuning.broadcast_estimate(spark, events, str(tmp_path / "u"))
    assert out["default_broadcast"] is True and out["half_file_size_broadcast"] is False
    assert out["file_bytes"] > 0 and "B" in out["estimate"]


def test_skew_ratio_and_the_three_fixes(spark, events, skewed, users):
    assert tuning.skew_ratio(events, ["user_id"]) < 1.5
    out = tuning.skew_join_fixes(spark, skewed, users)
    plain_tasks, plain_max, plain_median, plain_rows = out["plain"]
    assert out["ratio_before"] > 5 and out["ratio_after"] < out["ratio_before"] / 2
    assert out["salted"][3] == out["aqe"][3] == plain_rows == 1_000_000
    assert plain_max > 10 * plain_median  # 素の結合は、最大の reduce タスクが中央値の 10 倍以上
    assert out["salted"][1] < plain_max / 2 and out["aqe"][1] < plain_max / 2
    assert out["aqe"][0] > plain_tasks  # 偏ったパーティションがタスクに割られた


def test_partial_aggregation_absorbs_group_by_skew(spark, skewed):
    out = tuning.groupby_skew_needs_no_salt(spark, skewed)
    assert out["input_ratio"] > 5 and out["sum"][0] < 0.25 * 1_000_000
    sum_max, sum_median = out["sum"][2]
    list_max, list_median = out["collect_list"][2]
    assert sum_max < 1.5 * sum_median  # sum は読む量が均等
    assert list_max > 3 * list_median  # collect_list は偏った 1 タスクが重い


def test_small_file_counts(spark, events, tmp_path):
    out = tuning.small_file_writes(spark, events, str(tmp_path))
    assert out["repartition_by_date"] == out["repartition_1"] == out["repartition_4"] == 30
    assert out["plain"] > 3 * out["repartition_by_date"]
    assert out["capped_2000_rows"] > out["repartition_by_date"]
    assert (tuning.partitions_for(10_000), tuning.partitions_for(50)) == (78, 1)


def test_coalesce_pulls_the_whole_stage_into_one_task(spark, events):
    assert tuning.coalesce_limits_parallelism(spark, events) == {"coalesce": [1], "repartition": [4, 1]}


def test_many_small_files_are_not_faster(spark, events, tmp_path):
    out = tuning.read_many_files(spark, events, str(tmp_path))
    assert set(out) == {4, 200}
    assert tuning.count_files(tmp_path / "f200") == 200 and tuning.count_files(tmp_path / "f4") == 4


def test_cache_removes_the_file_scan_from_the_plan(spark, events, tmp_path):
    events.write.parquet(str(tmp_path / "e"))
    out = tuning.cache_effect(spark, str(tmp_path / "e"), 1)
    assert out["reads_file"] == {"plain": True, "cached": False}


def test_udf_kinds_show_up_in_the_plan(spark, events, tmp_path):
    out = tuning.udf_vs_builtin(spark, events)
    assert {k: v[0] for k, v in out.items()} == {
        "builtin": "なし", "python_classic": "BatchEvalPython", "python_arrow": "ArrowEvalPython", "pandas": "ArrowEvalPython"}
    assert all(v[1] for v in out.values())  # 4 通りとも結果が同じ
    events.write.parquet(str(tmp_path / "e"))
    builtin, udf = tuning.pushdown_lost(spark, str(tmp_path / "e"))
    assert "GreaterThanOrEqual(amount,5000)" in builtin and udf == ""


def test_small_heap_spills_and_hits_max_result_size():
    import subprocess
    root = Path(__file__).parent
    small = subprocess.run([sys.executable, str(root / "spill_demo.py"), "512m", "2000000"], capture_output=True, text=True, check=True)
    report = __import__("json").loads([l for l in small.stdout.splitlines() if l.startswith("{")][-1])
    assert report["spill_disk_mb"] > 0 and "maxResultSize" in report["max_result_size_error"]


def test_memory_layout_formula(spark):
    assert tuning.executor_memory_layout(8192) == {
        "heap": 8192, "reserved": 300, "usable": 7892, "unified": 4735.2, "storage_protected": 2367.6,
        "user": 3156.8, "overhead": 819, "container": 9011}
    assert tuning.executor_memory_layout(1024)["overhead"] == 384  # 下限
    formula, reported = tuning.unified_memory_in_this_jvm(spark)
    assert abs(formula - reported) / reported < 0.01


def test_case_study_fixes_one_thing_at_a_time(spark, tmp_path):
    a, b, c, d = tuning.case_study(spark, str(tmp_path), 300_000, repeat=1)
    assert a["files"] == b["files"] > 5 * c["files"] and c["files"] == d["files"] == 30
    assert a["max_reduce_rows"] > 5 * a["median_reduce_rows"]  # ボットの偏り
    assert d["max_reduce_rows"] < a["max_reduce_rows"]  # 配ると偏りが消える
    assert d["shuffle_mb"] < c["shuffle_mb"]  # 配ると大きい側が動かない


def test_exercise_memory_layout_of_a_4g_executor():
    layout = tuning.executor_memory_layout(4096)
    assert layout["overhead"] == 409 and layout["container"] == 4505
    assert layout["unified"] == 2277.6
