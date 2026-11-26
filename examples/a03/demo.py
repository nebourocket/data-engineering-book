"""第3章の出力を順に表示します: python examples/a03/demo.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import case_study  # noqa: E402
import delta_demo  # noqa: E402
import iceberg_demo  # noqa: E402
import plain_lake  # noqa: E402
import rowlevel  # noqa: E402


def tmp():
    return Path(tempfile.mkdtemp())


def emit(key, value):
    """本文に差し込む行には、先頭に [キー] を付けます。"""
    print(f"[{key}] {value}")


def fmt_row(row):
    return "  ".join(f"{k} {v}" for k, v in row.items())


def main():
    emit("plain-half", f"途中で読んだ行数, 書き終えた行数: {plain_lake.half_written_view(tmp())}")
    emit("plain-null", f"price 列: {plain_lake.silent_nulls(tmp())}")
    root = tmp()
    plain_lake.write_files(root, range(20))
    customer = plain_lake.make_batch(0, 10).column("customer_id")[0].as_py()
    emit("plain-delete", f"書き換えが要るファイル数, 全ファイル数: {plain_lake.files_to_rewrite_for_delete(root, customer)}")
    path = tmp() / "t"
    for row in delta_demo.story(path):
        emit("delta-story", fmt_row(row))
    emit("delta-log", f"版2のログ: {delta_demo.log_entry(path, 2)}  版3: {delta_demo.log_entry(path, 3)}")
    emit("delta-orphan", f"ログ外のファイル: {delta_demo.untracked_file_is_invisible(tmp() / 'u')}")
    emit("delta-travel", f"タイムトラベル: {delta_demo.time_travel(tmp() / 't')}")
    emit("delta-schema", f"スキーマ: {delta_demo.schema_changes(tmp() / 's')}")
    emit("delta-mapping", f"列マッピング: {delta_demo.column_mapping_names(tmp() / 'c')}")
    for key, value in delta_demo.deletion_vector_support(tmp() / "dv").items():
        emit("delta-dv", f"{key}: {value}")
    emit("delta-conflict", f"衝突: {delta_demo.conflict_matrix(tmp() / 'k')}")
    for row in iceberg_demo.story(tmp()):
        emit("ice-story", fmt_row(row))
    emit("ice-chain", f"連鎖: {iceberg_demo.chain(tmp())}")
    emit("ice-expire", f"期限切れ: {iceberg_demo.time_travel_and_expire(tmp())}")
    emit("ice-schema", f"スキーマ進化: {iceberg_demo.schema_evolution(tmp())}")
    emit("ice-partition", f"パーティション進化: {iceberg_demo.partition_evolution(tmp())}")
    emit("ice-day", f"day 変換: {iceberg_demo.hidden_partition_value()}")
    emit("ice-delete", f"一部だけ消す delete (操作, 削除ファイル数, 行数): {iceberg_demo.delete_operation(tmp())}")
    emit("ice-conflict", f"衝突 (再試行 0 / 4): {iceberg_demo.conflict(tmp(), 0)} {iceberg_demo.conflict(tmp(), 4)}")
    work = tmp()
    base = rowlevel.write_base(work / "base.parquet", 200_000)
    one, many = [5], list(range(0, 200_000, 100))
    for label, ids in (("1 行", one), ("1%", many)):
        cow = rowlevel.cow_delete(work / "base.parquet", work / "cow.parquet", ids)
        mor = rowlevel.mor_delete(work / "base.parquet", work / "del.parquet", ids)
        emit("rowlevel", f"{label} 元 {base} COW が書いた {cow} MOR が書いた {mor}")
    cost = rowlevel.read_cost(work, work / "base.parquet")
    for row in cost:
        emit("rowlevel-read", f"削除ファイル {row['delete_files']} 開くファイル {row['files_opened']}"
             f" 読む {row['seconds'] * 1000:.0f} ms (0 個の {row['seconds'] / cost[0]['seconds']:.1f} 倍)")
    d = case_study.delta_day(tmp() / "day")
    emit("case-delta", f"追加 288 回のあと: {d['after_appends']} 有効 {d['live']} データ合計 {d['bytes']} バイト"
         f" (1 ファイル平均 {d['bytes'] // d['live']} バイト)")
    emit("case-delta", f"コンパクションと vacuum のあと: {d['after_compact']} 有効 {d['live_after']} 行 {d['rows']}")
    emit("case-delta", f"全部を読む (3 回の最短): 前 {d['read_s'] * 1000:.0f} ms 後 {d['read_s_after'] * 1000:.0f} ms"
         f" 比 (前 ÷ 後) {d['read_s'] / d['read_s_after']:.0f}")
    i = case_study.iceberg_day(tmp())
    emit("case-ice", f"追加 288 回のあと: {i['after_appends']} スナップショット {i['snapshots']}"
         f" 現在のマニフェスト {i['manifests_in_current']}")
    emit("case-ice", f"全部を書き直したあと: {i['after_compact']} 有効 {i['live_after']}"
         f" 現在のマニフェスト {i['manifests_after']} 行 {i['rows']}")
    emit("case-ice", f"期限切れのあと: {i['after_expire']} スナップショット {i['snapshots_after_expire']}")
    emit("case-ice", f"全部を読む (3 回の最短): 前 {i['read_s'] * 1000:.0f} ms 後 {i['read_s_after'] * 1000:.0f} ms"
         f" 比 (前 ÷ 後) {i['read_s'] / i['read_s_after']:.0f}")
    emit("case-ice", f"開くデータファイル数: 前 {i['live']} 後 {i['live_after']}")


if __name__ == "__main__":
    main()
