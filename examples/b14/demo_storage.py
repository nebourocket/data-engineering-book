"""オブジェクトストレージの動きを順に見せる実演です (MinIO を動かしてから流します)。

  S3_ENDPOINT=http://localhost:9000 S3_ACCESS_KEY=minioadmin S3_SECRET_KEY=minioadmin \
      python examples/b14/demo_storage.py
"""
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "etl"))
sys.path.insert(0, str(HERE.parent / "common"))
from neboske_shop import generate  # noqa: E402
from storage import compact, list_folders, list_keys, make_client, write_partitions  # noqa: E402


def demo(client, bucket):
    rows = [r for r in generate()["events"] if r["event_time"] < "2026-01-04"]
    keys = write_partitions(client, bucket, "events", rows, rows_per_file=10)
    print("置いたキー数:", len(keys))
    print("フォルダに見えるもの:", list_folders(client, bucket, "events/"))
    one_day, pages = list_keys(client, bucket, "events/dt=2026-01-02/")
    print("1 日分のキー:", one_day, f"(LIST は {pages} 回)")
    _, pages = list_keys(client, bucket, "events/", page_size=2)
    print("全部を 2 件ずつ一覧すると LIST は", pages, "回")
    merged = compact(client, bucket, "events/dt=2026-01-02/")
    print("まとめた後:", list_keys(client, bucket, "events/dt=2026-01-02/")[0], "=", merged)


if __name__ == "__main__":
    client = make_client()
    bucket = f"demo-{uuid.uuid4().hex[:8]}"
    client.create_bucket(Bucket=bucket)
    try:
        demo(client, bucket)
    finally:
        for key in list_keys(client, bucket, "")[0]:
            client.delete_object(Bucket=bucket, Key=key)
        client.delete_bucket(Bucket=bucket)
