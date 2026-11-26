"""Apache Iceberg (pyiceberg + SQLite のカタログ) で、操作ごとに何が増えるかを数えます。"""
import datetime as dt
from datetime import timezone

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.transforms import DayTransform, IdentityTransform
from pyiceberg.types import LongType, TimestampType

from lake_events import SCHEMA, make_batch


def new_catalog(root):
    """カタログ (表の名前と、いまのメタデータファイルの場所を覚える SQLite) と倉庫フォルダを作ります。"""
    root.mkdir(parents=True, exist_ok=True)
    catalog = SqlCatalog("shop", uri=f"sqlite:///{root}/catalog.db", warehouse=f"file://{root}/warehouse")
    catalog.create_namespace("lake")
    return catalog


def count_files(root):
    """倉庫フォルダにあるファイルを種類ごとに数えます。"""
    counts = {"parquet": 0, "metadata.json": 0, "manifest-list": 0, "manifest": 0}
    for path in (root / "warehouse").rglob("*"):
        if path.suffix == ".parquet":
            counts["parquet"] += 1
        elif path.name.endswith(".metadata.json"):
            counts["metadata.json"] += 1
        elif path.name.startswith("snap-"):
            counts["manifest-list"] += 1
        elif path.suffix == ".avro":
            counts["manifest"] += 1
    return counts


def story(root):
    """作る → 追加 → 削除 → 上書き挿入 (upsert) → 列の追加 → 全部を書き直す、を順に行います。"""
    catalog = new_catalog(root)
    table = catalog.create_table("lake.events", schema=SCHEMA)
    rows = []

    def snap(label):
        current = catalog.load_table("lake.events")
        files = current.inspect.files().num_rows
        rows.append({"step": label, "snapshots": len(current.snapshots()), "live": files,
                     "rows": current.scan().to_arrow().num_rows, **count_files(root)})

    snap("作る")
    table.append(make_batch(0))
    table.append(make_batch(1))
    snap("追加 ×2")
    catalog.load_table("lake.events").delete("event_type = 'search'")
    snap("削除")
    catalog.load_table("lake.events").upsert(
        pa.concat_tables([make_batch(10, rows=5), make_batch(100, rows=3)]), join_cols=["event_id"])
    snap("upsert")
    with catalog.load_table("lake.events").update_schema() as update:
        update.add_column("coupon", LongType())
    snap("列の追加")
    current = catalog.load_table("lake.events")
    current.overwrite(current.scan().to_arrow().select(SCHEMA.names))
    snap("全部を書き直す")
    return rows


def chain(root):
    """カタログ → メタデータファイル → マニフェストリスト → マニフェスト → データ、の各段の数。"""
    catalog = new_catalog(root)
    table = catalog.create_table("lake.events", schema=SCHEMA)
    table.append(make_batch(0))
    table.append(make_batch(1))
    table = catalog.load_table("lake.events")
    snapshot = table.current_snapshot()
    return {
        "metadata_location": table.metadata_location.rsplit("/", 1)[-1],
        "snapshots_in_metadata": len(table.snapshots()),
        "manifest_list": snapshot.manifest_list.rsplit("/", 1)[-1],
        "manifests_in_list": len(table.inspect.manifests()),
        "data_files": table.inspect.files().num_rows,
    }


def time_travel_and_expire(root):
    """スナップショットごとの行数。期限切れにした後で、ファイルが残るかを数えます。"""
    catalog = new_catalog(root)
    table = catalog.create_table("lake.events", schema=SCHEMA)
    table.append(make_batch(0))
    table.append(make_batch(1))
    catalog.load_table("lake.events").delete("event_id < 50")
    table = catalog.load_table("lake.events")
    ids = [s.snapshot_id for s in table.snapshots()]
    before_rows = [table.scan(snapshot_id=i).to_arrow().num_rows for i in ids]
    before = count_files(root)
    cutoff = dt.datetime.now(timezone.utc) + dt.timedelta(seconds=5)
    table.maintenance.expire_snapshots().older_than(cutoff).commit()
    after_table = catalog.load_table("lake.events")
    return before_rows, len(after_table.snapshots()), before, count_files(root)


def schema_evolution(root):
    """列名の変更と型の広げ方 (int → long)。データファイルには手を付けません。"""
    catalog = new_catalog(root)
    schema = pa.schema([pa.field("event_id", pa.int32()), pa.field("region", pa.string())])
    table = catalog.create_table("lake.events", schema=schema)
    table.append(pa.table({"event_id": pa.array([1, 2], pa.int32()), "region": ["east", "west"]}))
    files_before = sorted(table.inspect.files().column("file_path").to_pylist())
    with table.update_schema() as update:
        update.rename_column("region", "area")
        update.update_column("event_id", LongType())
    table = catalog.load_table("lake.events")
    files_after = sorted(table.inspect.files().column("file_path").to_pylist())
    ids = [(field.field_id, field.name, str(field.field_type)) for field in table.schema().fields]
    return ids, files_before == files_after, table.scan().to_arrow().to_pylist()


def partition_evolution(root):
    """region で分けていた表を event_type 分けに変えても、古いファイルは古い分け方のまま残ります。"""
    catalog = new_catalog(root)
    table = catalog.create_table("lake.events", schema=SCHEMA)
    with table.update_spec() as update:
        update.add_field("region", IdentityTransform(), "region")
    table = catalog.load_table("lake.events")
    table.append(make_batch(0))
    with table.update_spec() as update:
        update.remove_field("region")
        update.add_field("event_type", IdentityTransform(), "event_type")
    table = catalog.load_table("lake.events")
    table.append(make_batch(1))
    table = catalog.load_table("lake.events")
    files = table.inspect.files().select(["spec_id"]).to_pylist()
    by_spec = {}
    for item in files:
        by_spec[item["spec_id"]] = by_spec.get(item["spec_id"], 0) + 1
    return sorted(table.specs()), by_spec, table.scan().to_arrow().num_rows


def hidden_partition_value():
    """day 変換は、タイムスタンプから「1970-01-01 からの日数」を計算します (利用者は列を足さない)。"""
    micros = int(dt.datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc).timestamp() * 1_000_000)
    day = DayTransform().transform(TimestampType())(micros)
    return day, (dt.date(1970, 1, 1) + dt.timedelta(days=day)).isoformat()


def conflict(root, retries):
    """同じスナップショットから始めた 2 つの書き込みのうち、後のものが成功するか。"""
    catalog = new_catalog(root)
    table = catalog.create_table("lake.events", schema=SCHEMA,
                                 properties={"commit.retry.num-retries": str(retries)})
    table.append(make_batch(0))
    first = catalog.load_table("lake.events")
    second = catalog.load_table("lake.events")
    first.append(make_batch(1))
    try:
        second.append(make_batch(2))
        return "成功", len(catalog.load_table("lake.events").snapshots())
    except Exception as exc:
        return type(exc).__name__, len(catalog.load_table("lake.events").snapshots())


def delete_operation(root):
    """行の一部だけを消す delete が、どんなスナップショットを作るか (削除ファイルの数も見ます)。"""
    catalog = new_catalog(root)
    table = catalog.create_table("lake.events", schema=SCHEMA)
    table.append(make_batch(0))
    table.append(make_batch(1))
    catalog.load_table("lake.events").delete("customer_id < 100")
    table = catalog.load_table("lake.events")
    last = table.current_snapshot().summary
    return str(last.operation), last.additional_properties["total-delete-files"], table.scan().to_arrow().num_rows
