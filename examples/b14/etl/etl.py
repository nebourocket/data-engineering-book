"""小さな ETL: JSON Lines の行動ログを、日付ごとの Parquet にして S3 互換ストレージへ置きます。

設定は環境変数だけで受け取ります (コンテナでもローカルでも同じ)。
  INPUT_PATH      入力の JSON Lines (既定 /data/events.jsonl)
  BUCKET          書き込み先のバケット
  PREFIX          バケット内の接頭辞 (既定 events)
  CREATE_BUCKET   1 ならバケットが無いときに作る (ローカルの MinIO 用。本番は IaC で作る)
  S3_ENDPOINT など  storage.make_client を参照
"""
import json
import os
from pathlib import Path

from storage import make_client, write_partitions


def main(env=None, client=None):
    env = os.environ if env is None else env
    rows = [json.loads(line) for line in Path(env.get("INPUT_PATH", "/data/events.jsonl"))
            .read_text(encoding="utf-8").splitlines()]
    client = client or make_client(env)
    bucket = env["BUCKET"]
    if env.get("CREATE_BUCKET") == "1":
        names = [b["Name"] for b in client.list_buckets()["Buckets"]]
        if bucket not in names:
            client.create_bucket(Bucket=bucket)
    keys = write_partitions(client, bucket, env.get("PREFIX", "events"), rows)
    print(f"{len(rows)} 行を {len(keys)} ファイルに書きました")
    return keys


if __name__ == "__main__":
    main()
