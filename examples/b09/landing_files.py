"""MinIO (S3 互換) の landing 領域にファイルを置き、パーティション単位で取り込み先に入れます。

置き場所の決まり:  landing/<ソース>/dt=<受信日>/part-0000.jsonl.gz
 - dt は「届いた日」 (event_time ではない)。遅れて届いたデータも、届いた日のパーティションに入る。
 - キー名が日付だけで決まるので、同じ日をもう一度書いても同じキーに上書きされる (冪等)。
"""
import gzip
import json
from datetime import datetime, timezone

import pyarrow as pa

KNOWN_COLUMNS = ["event_id", "customer_id", "event_type", "event_time", "received_at"]


def partition_key(source, dt):
    return f"landing/{source}/dt={dt}/part-0000.jsonl.gz"


def land_events(s3, bucket, events):
    """events を受信日ごとにまとめて、gzip 圧縮の JSON Lines で置きます。置いた日付の一覧を返します。"""
    by_day = {}
    for event in events:
        by_day.setdefault(event["received_at"][:10], []).append(event)
    for dt, rows in by_day.items():
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
        s3.put_object(Bucket=bucket, Key=partition_key("events", dt), Body=gzip.compress(body))
        # 全部置き終えた印。読む側は、この印があるパーティションだけを読む
        s3.put_object(Bucket=bucket, Key=f"landing/events/dt={dt}/_SUCCESS", Body=b"")
    return sorted(by_day)


def list_ready_partitions(s3, bucket, source, after_dt=""):
    """_SUCCESS のあるパーティションの日付を、after_dt より後のものだけ、古い順に返します。"""
    found = set()
    paginator = s3.get_paginator("list_objects_v2")  # 1 回の list は最大 1,000 件なので、ページ送りが要る
    for page in paginator.paginate(Bucket=bucket, Prefix=f"landing/{source}/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith("/_SUCCESS"):
                found.add(obj["Key"].split("dt=")[1].split("/")[0])
    return sorted(dt for dt in found if dt > after_dt)


def split_known(record, known=KNOWN_COLUMNS):
    """想定の列と、想定外の列 (extra) に分けます。想定外の列があっても止まらず、失いもしません。"""
    return ({c: record.get(c) for c in known},
            {k: v for k, v in record.items() if k not in known})


def setup_raw(duck):
    duck.execute("""
        CREATE TABLE IF NOT EXISTS events_raw (
            event_id INTEGER, customer_id INTEGER, event_type VARCHAR,
            event_time VARCHAR, received_at VARCHAR,
            extra VARCHAR,            -- 想定外の列を JSON 文字列で残す
            dt VARCHAR,               -- 取り込んだパーティション
            source_file VARCHAR,      -- どのファイルから来たか
            ingested_at TIMESTAMPTZ   -- いつ取り込んだか
        )""")


def load_partition(duck, s3, bucket, dt):
    """1 つのパーティションを置き換えます (消してから入れる。1 トランザクション)。件数を返します。"""
    key = partition_key("events", dt)
    text = gzip.decompress(s3.get_object(Bucket=bucket, Key=key)["Body"].read()).decode("utf-8")
    now = datetime.now(timezone.utc)
    rows = []
    for line in text.splitlines():
        known, extra = split_known(json.loads(line))
        rows.append({**known, "extra": json.dumps(extra, ensure_ascii=False) if extra else None,
                     "dt": dt, "source_file": key, "ingested_at": now})
    batch = pa.Table.from_pylist(rows)
    duck.execute("BEGIN")
    try:
        duck.execute("DELETE FROM events_raw WHERE dt = ?", [dt])
        duck.register("batch", batch)
        duck.execute("INSERT INTO events_raw SELECT * FROM batch")
        duck.unregister("batch")
        duck.execute("COMMIT")
    except Exception:
        duck.execute("ROLLBACK")
        raise
    return len(rows)
