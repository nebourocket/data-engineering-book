"""ケーススタディ: 5 分ごとの取り込みで、小さなファイルがたまる様子と、コンパクションの効果を数えます。"""
import datetime as dt
import time
from datetime import timezone

import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

import delta_demo
import iceberg_demo
from lake_events import SCHEMA, make_batch


def seconds_to_read(read):
    """3 回読んで、いちばん短かった秒数 (相対比較にだけ使います)。"""
    best = None
    for _ in range(3):
        start = time.perf_counter()
        read()
        elapsed = time.perf_counter() - start
        best = elapsed if best is None else min(best, elapsed)
    return best


def delta_day(path, batches=288):
    """Delta Lake: 5 分ごとの追加 → チェックポイント → コンパクション → vacuum。"""
    for n in range(batches):
        write_deltalake(str(path), make_batch(n), mode="append")
    table = DeltaTable(str(path))
    result = {"after_appends": delta_demo.count_files(path), "live": len(table.file_uris()),
              "bytes": sum(f.stat().st_size for f in path.glob("*.parquet")),
              "read_s": seconds_to_read(lambda: DeltaTable(str(path)).to_pyarrow_table())}
    table.create_checkpoint()
    result["with_checkpoint"] = delta_demo.count_files(path)
    DeltaTable(str(path)).optimize.compact()
    time.sleep(1.1)  # vacuum は削除から時間がたったファイルだけを消します
    DeltaTable(str(path)).vacuum(retention_hours=0, enforce_retention_duration=False, dry_run=False)
    table = DeltaTable(str(path))
    result["after_compact"] = delta_demo.count_files(path)
    result["live_after"] = len(table.file_uris())
    result["rows"] = table.to_pyarrow_table().num_rows
    result["read_s_after"] = seconds_to_read(lambda: DeltaTable(str(path)).to_pyarrow_table())
    return result


def iceberg_day(root, batches=288):
    """Iceberg: 5 分ごとの追加 → 全部を書き直すコンパクション → スナップショットの期限切れ。"""
    catalog = iceberg_demo.new_catalog(root)
    table = catalog.create_table("lake.events", schema=SCHEMA)
    for n in range(batches):
        table.append(make_batch(n))
    table = catalog.load_table("lake.events")
    result = {"after_appends": iceberg_demo.count_files(root), "snapshots": len(table.snapshots()),
              "manifests_in_current": len(table.inspect.manifests()),
              "live": table.inspect.files().num_rows,
              "read_s": seconds_to_read(lambda: catalog.load_table("lake.events").scan().to_arrow())}
    table.overwrite(table.scan().to_arrow())
    table = catalog.load_table("lake.events")
    result["after_compact"] = iceberg_demo.count_files(root)
    result["live_after"] = table.inspect.files().num_rows
    result["manifests_after"] = len(table.inspect.manifests())
    result["rows"] = table.scan().to_arrow().num_rows
    result["read_s_after"] = seconds_to_read(lambda: catalog.load_table("lake.events").scan().to_arrow())
    cutoff = dt.datetime.now(timezone.utc) + dt.timedelta(seconds=5)
    table.maintenance.expire_snapshots().older_than(cutoff).commit()
    result["snapshots_after_expire"] = len(catalog.load_table("lake.events").snapshots())
    result["after_expire"] = iceberg_demo.count_files(root)
    return result
