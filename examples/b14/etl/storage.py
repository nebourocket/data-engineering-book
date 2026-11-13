"""オブジェクトストレージ (S3 互換) を boto3 で扱う小さな関数集です。

接続先は環境変数だけで切り替えます。S3_ENDPOINT があれば MinIO などの互換サーバー、
無ければ AWS の S3 に繋ぎます。コードはローカルでも本番でも同じです。
"""
import io
import os
from collections import defaultdict

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

MIB = 1024 * 1024


def make_client(env=None):
    env = os.environ if env is None else env
    kwargs = {"region_name": env.get("S3_REGION", "us-east-1")}
    if env.get("S3_ENDPOINT"):
        kwargs["endpoint_url"] = env["S3_ENDPOINT"]
        kwargs["config"] = Config(s3={"addressing_style": "path"})  # MinIO はパス形式
    if env.get("S3_ACCESS_KEY"):  # 無ければ boto3 の標準の探し方 (環境変数・ロール) に任せる
        kwargs["aws_access_key_id"] = env["S3_ACCESS_KEY"]
        kwargs["aws_secret_access_key"] = env["S3_SECRET_KEY"]
    return boto3.client("s3", **kwargs)


def hive_key(prefix, dt, part):
    """Hive 形式のキー。例: events/dt=2026-03-01/part-0000.parquet"""
    return f"{prefix}/dt={dt}/part-{part:04d}.parquet"


def _to_parquet_bytes(rows):
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buf)
    return buf.getvalue()


def write_partitions(client, bucket, prefix, rows, time_col="event_time", rows_per_file=None):
    """rows を日付 (time_col の先頭 10 文字) ごとの Parquet にして置き、キーの一覧を返します。"""
    by_day = defaultdict(list)
    for row in rows:
        by_day[row[time_col][:10]].append(row)
    keys = []
    for dt, day_rows in sorted(by_day.items()):
        size = rows_per_file or len(day_rows)
        for part, start in enumerate(range(0, len(day_rows), size)):
            key = hive_key(prefix, dt, part)
            client.put_object(Bucket=bucket, Key=key, Body=_to_parquet_bytes(day_rows[start:start + size]))
            keys.append(key)
    return keys


def list_keys(client, bucket, prefix, page_size=1000):
    """prefix で始まるキーを全部返します。(キー一覧, LIST リクエストの回数)。"""
    paginator = client.get_paginator("list_objects_v2")
    keys, pages = [], 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, PaginationConfig={"PageSize": page_size}):
        pages += 1
        keys += [obj["Key"] for obj in page.get("Contents", [])]
    return keys, pages


def list_folders(client, bucket, prefix):
    """区切り文字 "/" で 1 階層分だけ見て、「フォルダに見えるもの」を返します。"""
    paginator = client.get_paginator("list_objects_v2")
    out = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        out += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
    return out


def compact(client, bucket, partition_prefix):
    """prefix 配下の小さな Parquet を 1 つにまとめます。先に書いてから古いものを消します。"""
    keys, _ = list_keys(client, bucket, partition_prefix)
    tables = [pq.read_table(io.BytesIO(client.get_object(Bucket=bucket, Key=k)["Body"].read()))
              for k in keys]
    merged = pa.concat_tables(tables)
    buf = io.BytesIO()
    pq.write_table(merged, buf)
    new_key = f"{partition_prefix}compacted.parquet"
    client.put_object(Bucket=bucket, Key=new_key, Body=buf.getvalue())
    old = [{"Key": k} for k in keys if k != new_key]
    for i in range(0, len(old), 1000):  # delete_objects は 1 回 1000 件まで
        client.delete_objects(Bucket=bucket, Delete={"Objects": old[i:i + 1000]})
    return new_key


def upload_large(client, bucket, key, path, threshold=5 * MIB):
    """threshold を超えるファイルは自動でマルチパート (分割) アップロードになります。ETag を返します。"""
    config = TransferConfig(multipart_threshold=threshold, multipart_chunksize=threshold)
    client.upload_file(str(path), bucket, key, Config=config)
    return client.head_object(Bucket=bucket, Key=key)["ETag"].strip('"')


def presigned_get(client, bucket, key, seconds=60):
    """認証情報を渡さずに、期限付きで 1 つのオブジェクトだけ読める URL を作ります。"""
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=seconds)


def expire_prefix_after(client, bucket, prefix, days):
    """prefix 配下のオブジェクトを days 日後に自動で消すライフサイクル規則を設定します。"""
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={"Rules": [{
            "ID": f"expire-{prefix.strip('/').replace('/', '-')}",
            "Filter": {"Prefix": prefix},
            "Status": "Enabled",
            "Expiration": {"Days": days},
        }]})
