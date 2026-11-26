"""第3章のコードの検査。ファイル・版・スナップショットの数だけを確かめます (秒数は見ません)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import case_study  # noqa: E402
import delta_demo  # noqa: E402
import iceberg_demo  # noqa: E402
import plain_lake  # noqa: E402
import rowlevel  # noqa: E402


def test_plain_folder_problems(tmp_path):
    (tmp_path / "a").mkdir()
    assert plain_lake.half_written_view(tmp_path / "a") == (20, 30)
    (tmp_path / "b").mkdir()
    assert plain_lake.silent_nulls(tmp_path / "b") == [100, 200, None, None]
    (tmp_path / "c").mkdir()
    plain_lake.write_files(tmp_path / "c", range(20))
    touched, total = plain_lake.files_to_rewrite_for_delete(
        tmp_path / "c", plain_lake.make_batch(0, 10).column("customer_id")[0].as_py())
    assert total == 20 and touched >= 1


def test_delta_story_counts(tmp_path):
    rows = {r["step"]: r for r in delta_demo.story(tmp_path / "t")}
    assert rows["作る"]["version"] == 0 and rows["追加"]["live"] == 2
    assert rows["小さな追加 ×3"]["live"] == rows["MERGE"]["live"] + 3
    assert rows["コンパクション"]["live"] == 1
    # 古いファイルは消えない: 読める版が増えるほどディスクの Parquet は増える
    assert rows["コンパクション"]["parquet"] > rows["コンパクション"]["live"]
    assert rows["コンパクション"]["json"] == rows["コンパクション"]["version"] + 1
    assert delta_demo.log_entry(tmp_path / "t", 2) == {"commitInfo": 1, "add": 1, "remove": 1}


def test_delta_orphan_vacuum_and_time_travel(tmp_path):
    rows, removable = delta_demo.untracked_file_is_invisible(tmp_path / "u")
    assert rows == 50 and removable == ["orphan.parquet"]
    before, after, parquet_left = delta_demo.time_travel(tmp_path / "t")
    assert before == [50, 100, 50] and after == "FileNotFoundError" and parquet_left == 1


def test_delta_schema_and_mapping(tmp_path):
    plain, names, nulls, mismatch = delta_demo.schema_changes(tmp_path / "s")
    assert plain == "SchemaMismatchError" and names[-1] == "coupon" and nulls == 50
    assert "Cannot cast" in mismatch
    mapping = delta_demo.column_mapping_names(tmp_path / "c")
    assert [m[0] for m in mapping] == ["event_id", "region"]
    assert all(m[1].startswith("col-") for m in mapping)


def test_delta_deletion_vectors_not_written_by_delta_rs_delete(tmp_path):
    result = delta_demo.deletion_vector_support(tmp_path / "dv")
    assert result["copied"] == 42 and result["deleted"] == 8 and not result["dv_in_log"]
    assert "deletionVectors" in result["reader_features"]
    assert result["pyarrow"].startswith("DeltaProtocolError") and "deletionVectors" in result["pyarrow"]
    assert result["querybuilder_rows"] == 42


def test_delta_conflicts(tmp_path):
    assert delta_demo.conflict_matrix(tmp_path / "k") == {
        "追加と追加": "成功", "別の日の更新どうし": "成功",
        "同じ日の更新どうし": "CommitFailedError", "追加のあとの更新": "成功"}


def test_iceberg_story_and_chain(tmp_path):
    rows = {r["step"]: r for r in iceberg_demo.story(tmp_path / "s")}
    assert rows["作る"]["snapshots"] == 0 and rows["追加 ×2"]["snapshots"] == 2
    assert rows["追加 ×2"]["manifest"] == 2 and rows["追加 ×2"]["metadata.json"] == 3
    assert rows["列の追加"]["snapshots"] == rows["upsert"]["snapshots"]
    assert rows["全部を書き直す"]["live"] == 1
    chain = iceberg_demo.chain(tmp_path / "c")
    assert chain["snapshots_in_metadata"] == 2 and chain["manifests_in_list"] == 2


def test_iceberg_expire_keeps_files(tmp_path):
    rows, snapshots_left, before, after = iceberg_demo.time_travel_and_expire(tmp_path / "e")
    assert rows == [50, 100, 50] and snapshots_left == 1
    assert after["parquet"] == before["parquet"] and after["manifest-list"] == before["manifest-list"]


def test_iceberg_partial_delete_rewrites_files(tmp_path):
    assert iceberg_demo.delete_operation(tmp_path) == ("Operation.OVERWRITE", "0", 81)


def test_iceberg_schema_partition_conflict(tmp_path):
    ids, same_files, rows = iceberg_demo.schema_evolution(tmp_path / "a")
    assert ids == [(1, "event_id", "long"), (2, "area", "string")] and same_files
    assert rows[0] == {"event_id": 1, "area": "east"}
    specs, by_spec, total = iceberg_demo.partition_evolution(tmp_path / "b")
    assert specs == [0, 1, 2] and by_spec == {1: 2, 2: 4} and total == 100
    assert iceberg_demo.hidden_partition_value() == (20635, "2026-07-01")
    assert iceberg_demo.conflict(tmp_path / "c0", 0) == ("CommitFailedException", 2)
    assert iceberg_demo.conflict(tmp_path / "c4", 4) == ("成功", 3)


def test_copy_on_write_versus_merge_on_read(tmp_path):
    base = rowlevel.write_base(tmp_path / "b.parquet", 50_000)
    cow = rowlevel.cow_delete(tmp_path / "b.parquet", tmp_path / "c.parquet", [5])
    mor = rowlevel.mor_delete(tmp_path / "b.parquet", tmp_path / "d.parquet", [5])
    assert cow > base * 0.9 and mor < base / 100
    assert rowlevel.read_with_deletes(tmp_path / "b.parquet", tmp_path / "d.parquet").num_rows == 49_999


def test_merge_on_read_read_cost_grows_with_delete_files(tmp_path):
    base = tmp_path / "b.parquet"
    rowlevel.write_base(base, 50_000)
    cost = {r["delete_files"]: r for r in rowlevel.read_cost(tmp_path, base)}
    assert [cost[n]["files_opened"] for n in (0, 1, 10, 100)] == [1, 2, 11, 101]
    assert [cost[n]["rows"] for n in (0, 1, 10, 100)] == [50_000, 49_990, 49_900, 49_000]
    assert cost[100]["seconds"] > cost[0]["seconds"]


def test_case_study_small(tmp_path):
    d = case_study.delta_day(tmp_path / "d", batches=24)
    assert d["after_appends"]["parquet"] == 24 and d["live_after"] == 1 and d["rows"] == 24 * 50
    assert d["after_compact"]["parquet"] == 1
    i = case_study.iceberg_day(tmp_path / "i", batches=24)
    assert i["snapshots"] == 24 and i["manifests_in_current"] == 24
    assert i["live_after"] == 1 and i["manifests_after"] == 1 and i["rows"] == 24 * 50
    assert i["after_expire"]["parquet"] == i["after_compact"]["parquet"]
