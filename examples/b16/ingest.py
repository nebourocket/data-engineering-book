"""取り込み: ねぼすけ商店の表を landing に置き、DuckDB の raw 表に読み込みます。

 - events は第9章の landing_files.py をそのまま使います (受信日ごとの dt=<日付> と、日ごとの _SUCCESS)。
 - customers・orders・order_items は、同じ決まりで raw/dt=<取り込み日>/<表名>.parquet に置きます。
置き場所の決まり (第9章):
 - 同じ dt で何度実行しても、同じキーを上書きするだけ (冪等)。
 - 全部置き終えた印 (_SUCCESS) は最後に置く。再実行のときは、置き直す前に前回の印を消す
   (消さないと、置き直しの途中で止まったとき、古い印のせいで書きかけを読めてしまう)。
 - 読む側は印が無い dt を読まない。
 - raw 表は、元の値を加工せずに入れる (表記ゆれや重複も、そのまま)。直すのは次の変換 (dbt) の仕事。
"""
import io
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples" / "b09"))  # 第9章のコードは、フォルダの中の名前でそのまま読み込む
import landing_files  # noqa: E402  (第9章)
from examples.common.neboske_shop import generate  # noqa: E402

TABLES = ["customers", "orders", "order_items"]


def success_key(dt):
    return f"raw/dt={dt}/_SUCCESS"


def land(s3, bucket, dt):
    """TABLES を Parquet にして置き、events は第9章の land_events で置きます。印は最後です。"""
    data = generate()
    s3.delete_object(Bucket=bucket, Key=success_key(dt))  # 置き直す前に、前回の印を消す
    for name in TABLES:
        buf = io.BytesIO()
        pq.write_table(pa.Table.from_pylist(data[name]), buf)
        s3.put_object(Bucket=bucket, Key=f"raw/dt={dt}/{name}.parquet", Body=buf.getvalue())
    landing_files.land_events(s3, bucket, data["events"])  # 日ごとの _SUCCESS も、置き終えたあとに置かれる
    s3.put_object(Bucket=bucket, Key=success_key(dt), Body=b"")


def load_raw(con, s3, bucket, dt):
    """印のある dt だけを、DuckDB の raw 表 (main スキーマ) に読み込みます。件数の辞書を返します。"""
    keys = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=success_key(dt))
            for o in page.get("Contents", [])]
    if success_key(dt) not in keys:
        raise RuntimeError(f"dt={dt} は _SUCCESS が無いので読みません (書きかけかもしれません)")
    counts = {}
    for name in TABLES:
        body = s3.get_object(Bucket=bucket, Key=f"raw/dt={dt}/{name}.parquet")["Body"].read()
        con.register("_t", pq.read_table(io.BytesIO(body)))
        con.execute(f"CREATE OR REPLACE TABLE main.{name} AS SELECT * FROM _t")
        con.unregister("_t")
        counts[name] = con.execute(f"SELECT count(*) FROM main.{name}").fetchall()[0][0]
    # events: 第9章の load_partition で events_raw に入れ、dbt が読む main.events (元の 5 列) を作る
    landing_files.setup_raw(con)
    landing_files.load_new_partitions(con, s3, bucket)
    con.execute("""CREATE OR REPLACE TABLE main.events AS
                   SELECT event_id, customer_id, event_type, event_time, received_at FROM events_raw""")
    counts["events"] = con.execute("SELECT count(*) FROM main.events").fetchall()[0][0]
    return counts
