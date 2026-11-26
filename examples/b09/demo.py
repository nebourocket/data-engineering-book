"""本文の出力例を作る実行スクリプト。PG_DSN と S3_ENDPOINT などの環境変数が要ります。

使い方: python examples/b09/demo.py
"""
import os
import sys
import uuid
from pathlib import Path

import api_client
import boto3
import duckdb
import fake_api
import incremental_load as inc
import landing_files as landing
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import generate  # noqa: E402

data = generate()

print("--- REST API")
waits = []
with fake_api.FakeApi(data["orders"], reject_first=2) as api:
    rows = api_client.fetch_all(api.url, fake_api.TOKEN, limit=500, sleep=waits.append)
    print(f"取得 {len(rows)} 件, リクエスト {api.requests} 回, 待った秒数 {waits}")

print("--- 差分の取り込み")
dsn = os.environ["PG_DSN"]
inc.setup_source(dsn)
duck = duckdb.connect()
inc.setup_target(duck)
print("1 回目:", inc.load(duck, dsn), "件")
print("2 回目:", inc.load(duck, dsn), "件")
with psycopg.connect(dsn) as con:
    con.execute("UPDATE b09.orders SET status = 'cancelled', updated_at = now() WHERE order_id IN (1, 2)")
    con.execute("INSERT INTO b09.orders VALUES (9001, 1, 'placed', 1000, now())")
print("変更後:", inc.load(duck, dsn), "件")
duck.execute("DELETE FROM watermark")  # ウォーターマークの行を消すと 1970 年に戻り、全件を読み直す
print("全件を読み直した後の行数:", inc.load(duck, dsn), "件読んで",
      duck.execute("SELECT count(*) FROM orders").fetchone()[0], "行")

print("--- landing (MinIO)")
s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], region_name="us-east-1",
                  aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
                  aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"))
bucket = f"demo-{uuid.uuid4().hex[:8]}"
s3.create_bucket(Bucket=bucket)
days = landing.land_events(s3, bucket, data["events"])
print("置いたパーティション:", len(days), "日分", days[0], "〜", days[-1])
landing.setup_raw(duck)
for dt in days:
    landing.load_partition(duck, s3, bucket, dt)
print("raw の行数と event_id の種類:", duck.execute("SELECT count(*), count(DISTINCT event_id) FROM events_raw").fetchone())
print("event_time の日付と dt が違う行:", duck.execute(
    "SELECT count(*) FROM events_raw WHERE substr(event_time, 1, 10) <> dt").fetchone()[0])
for _ in range(2):
    landing.load_partition(duck, s3, bucket, days[10])
print("同じ日を入れ直した後の行数:", duck.execute("SELECT count(*) FROM events_raw").fetchone()[0])
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
    for obj in page.get("Contents", []):
        s3.delete_object(Bucket=bucket, Key=obj["Key"])
s3.delete_bucket(Bucket=bucket)
