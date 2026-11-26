"""Delta Lake (delta-rs の Python 版 deltalake) で、操作ごとに何が増えるかを数えます。"""
import json
import time

import pyarrow as pa
import pyarrow.parquet as pq
from deltalake import DeltaTable, QueryBuilder, write_deltalake

from lake_events import make_batch


def count_files(path):
    """表のフォルダにある、種類ごとのファイル数。"""
    log = sorted((path / "_delta_log").iterdir())
    checkpoints = sum(f.name.endswith(".checkpoint.parquet") for f in log)
    return {
        "parquet": len(list(path.rglob("*.parquet"))) - checkpoints,
        "json": sum(f.name.endswith(".json") for f in log),
        "checkpoint": checkpoints,
    }


def story(path):
    """作る → 追加 → 更新 → MERGE → 削除 → コンパクションを順に行い、各段階の数を返します。"""
    rows = []

    def snap(label):
        table = DeltaTable(str(path))
        counts = count_files(path)
        rows.append({"step": label, "version": table.version(), "live": len(table.file_uris()),
                     "rows": table.to_pyarrow_table().num_rows, **counts})

    write_deltalake(str(path), make_batch(0))
    snap("作る")
    write_deltalake(str(path), make_batch(1), mode="append")
    snap("追加")
    DeltaTable(str(path)).update({"event_type": "'view'"}, predicate="event_id < 10")
    snap("更新")
    DeltaTable(str(path)).delete("event_type = 'search'")
    snap("削除")
    # 一致する 5 行 (event_id 50〜54) と、新しい 3 行 (300〜302)
    source = pa.concat_tables([make_batch(10, rows=5), make_batch(100, rows=3)])
    (DeltaTable(str(path)).merge(source, predicate="t.event_id = s.event_id",
                                 source_alias="s", target_alias="t")
     .when_matched_update_all().when_not_matched_insert_all().execute())
    snap("MERGE")
    for n in (2, 3, 4):
        write_deltalake(str(path), make_batch(n, rows=5), mode="append")
    snap("小さな追加 ×3")
    DeltaTable(str(path)).optimize.compact()
    snap("コンパクション")
    return rows


def log_entry(path, version):
    """コミット 1 件の JSON ログを、種類 (add / remove / commitInfo …) ごとに数えます。"""
    kinds = {}
    for line in (path / "_delta_log" / f"{version:020d}.json").read_text().splitlines():
        kind = next(iter(json.loads(line)))
        kinds[kind] = kinds.get(kind, 0) + 1
    return kinds


def untracked_file_is_invisible(path):
    """ログに載せていない Parquet を置いても、表の行数は変わらない (書きかけの残骸)。"""
    write_deltalake(str(path), make_batch(0))
    pq.write_table(make_batch(9), path / "orphan.parquet")
    table = DeltaTable(str(path))
    removable = table.vacuum(retention_hours=0, enforce_retention_duration=False, dry_run=True, full=True)
    return table.to_pyarrow_table().num_rows, removable


def time_travel(path):
    """版ごとの行数。vacuum のあとで古い版を読むと失敗します。"""
    write_deltalake(str(path), make_batch(0))
    write_deltalake(str(path), make_batch(1), mode="append")
    DeltaTable(str(path)).delete("event_id < 50")
    before = [DeltaTable(str(path), version=v).to_pyarrow_table().num_rows for v in range(3)]
    time.sleep(1.1)  # vacuum は「削除した時刻」が保持期間より前のファイルだけを消すので、少し待ちます
    DeltaTable(str(path)).vacuum(retention_hours=0, enforce_retention_duration=False, dry_run=False)
    try:
        DeltaTable(str(path), version=0).to_pyarrow_table()
        after = "読めた"
    except Exception as exc:
        after = type(exc).__name__
    return before, after, count_files(path)["parquet"]


def schema_changes(path):
    """列の追加は受け入れ、型の食い違いは拒否します。"""
    write_deltalake(str(path), make_batch(0))
    wider = make_batch(1).append_column("coupon", pa.array(["c"] * 50))
    try:
        write_deltalake(str(path), wider, mode="append")
        plain = "受け入れた"
    except Exception as exc:
        plain = type(exc).__name__
    write_deltalake(str(path), wider, mode="append", schema_mode="merge")
    table = DeltaTable(str(path))
    nulls = table.to_pyarrow_table().column("coupon").null_count
    bad = make_batch(2).set_column(1, "customer_id", pa.array(["x"] * 50))
    try:
        write_deltalake(str(path), bad, mode="append", schema_mode="merge")
        mismatch = "受け入れた"
    except Exception as exc:
        mismatch = str(exc)[:90]
    return plain, [f.name for f in table.schema().fields], nulls, mismatch


def column_mapping_names(path):
    """列マッピング (name モード) では、論理名と物理名が別々に記録されます。"""
    write_deltalake(str(path), make_batch(0).select(["event_id", "region"]),
                    configuration={"delta.columnMapping.mode": "name"})
    first = (path / "_delta_log" / f"{0:020d}.json").read_text().splitlines()
    meta = next(json.loads(x) for x in first if "metaData" in x)["metaData"]
    fields = json.loads(meta["schemaString"])["fields"]
    return [(f["name"], f["metadata"]["delta.columnMapping.physicalName"]) for f in fields]


def conflict_matrix(path):
    """同じ版から始めた 2 つの書き手を、後から 1 つずつコミットさせたときの成否。"""
    outcomes = {}

    def fresh():
        write_deltalake(str(path), make_batch(0).append_column("day", pa.array(["d1"] * 25 + ["d2"] * 25)),
                        mode="overwrite", partition_by=["day"])
        return DeltaTable(str(path)), DeltaTable(str(path))

    def attempt(label, first, second):
        a, b = fresh()
        first(a)
        try:
            second(b)
            outcomes[label] = "成功"
        except Exception as exc:
            outcomes[label] = type(exc).__name__

    def append(table):
        extra = make_batch(5, rows=3).append_column("day", pa.array(["d3"] * 3))
        write_deltalake(table, extra, mode="append")

    def update(day):
        return lambda table: table.update({"event_type": "'view'"}, predicate=f"day = '{day}'")

    attempt("追加と追加", append, append)
    attempt("別の日の更新どうし", update("d1"), update("d2"))
    attempt("同じ日の更新どうし", update("d1"), update("d1"))
    attempt("追加のあとの更新", append, update("d1"))
    return outcomes


def deletion_vector_support(path):
    """削除ベクトルを有効にした表で、delta-rs の delete が何を書くか、どの読み方なら読めるかを調べます。"""
    write_deltalake(str(path), make_batch(0), configuration={"delta.enableDeletionVectors": "true"})
    table = DeltaTable(str(path))
    metrics = table.delete("customer_id < 100")
    log = (path / "_delta_log" / f"{table.version():020d}.json").read_text()
    result = {"copied": metrics["num_copied_rows"], "deleted": metrics["num_deleted_rows"],
              "dv_in_log": '"deletionVector"' in log,
              "reader_features": sorted(DeltaTable(str(path)).protocol().reader_features or [])}
    try:
        DeltaTable(str(path)).to_pyarrow_table()
        result["pyarrow"] = "読めた"
    except Exception as exc:
        result["pyarrow"] = f"{type(exc).__name__}: {exc}"
    counted = QueryBuilder().register("t", DeltaTable(str(path))).execute("select count(*) c from t").read_all()
    result["querybuilder_rows"] = counted.column("c")[0].as_py()
    return result
