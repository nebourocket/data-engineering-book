"""ローカルのディスクと MinIO で、追記・改名・上書きがどう違うかを確かめ、ライフサイクル規則を MinIO に渡します。"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "etl"))
import storage  # noqa: E402


def local_ops(workdir):
    """ローカルのファイルで、追記と改名をします。"""
    path = Path(workdir) / "log.txt"
    path.write_text("a\nb\n")
    inode = path.stat().st_ino
    with open(path, "a") as f:  # 末尾に足すだけ。既存の中身は読み直さない
        f.write("c\n")
    renamed = Path(workdir) / "log-new.txt"
    path.rename(renamed)  # 名前の付け替え。中身は動かない
    return {"追記後のバイト数": renamed.stat().st_size, "追記しても同じファイルか": renamed.stat().st_ino == inode,
            "改名後に旧名が残るか": path.exists()}


def object_ops(client, bucket):
    """同じことをオブジェクトでします。追記も改名も無いので、置き直しと、コピー + 削除になります。"""
    client.put_object(Bucket=bucket, Key="log.txt", Body=b"a\nb\n")
    first = client.head_object(Bucket=bucket, Key="log.txt")["ETag"]
    body = client.get_object(Bucket=bucket, Key="log.txt")["Body"].read()  # 追記には全部読み直す
    client.put_object(Bucket=bucket, Key="log.txt", Body=body + b"c\n")
    second = client.head_object(Bucket=bucket, Key="log.txt")["ETag"]
    client.copy_object(Bucket=bucket, Key="log-new.txt", CopySource={"Bucket": bucket, "Key": "log.txt"})
    between = sorted(o["Key"] for o in client.list_objects_v2(Bucket=bucket)["Contents"])
    client.delete_object(Bucket=bucket, Key="log.txt")
    return {"追記後のバイト数": client.head_object(Bucket=bucket, Key="log-new.txt")["ContentLength"],
            "追記で ETag が変わったか": first != second, "コピー直後のキー": between,
            "改名後のキー": sorted(o["Key"] for o in client.list_objects_v2(Bucket=bucket)["Contents"])}


def count_rows_elsewhere(bucket, key):
    """別のプロセス (計算) を新しく起こして、置いてあるオブジェクトの行数を数えます。"""
    code = ("import io, sys, pyarrow.parquet as pq; sys.path.insert(0, sys.argv[3]); import storage; "
            "c = storage.make_client(); "
            "print(pq.read_table(io.BytesIO(c.get_object(Bucket=sys.argv[1], Key=sys.argv[2])['Body'].read())).num_rows)")
    out = subprocess.run([sys.executable, "-c", code, bucket, key, str(HERE / "etl")],
                         check=True, capture_output=True, text=True, env=os.environ)
    return int(out.stdout)


def load_rules(path=HERE / "lifecycle.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def without_transitions(rules):
    """MinIO 単体には移す先の記憶域が無いので、移行 (Transitions) を除いた規則にします。"""
    return {"Rules": [{k: v for k, v in r.items() if k != "Transitions"} for r in rules["Rules"]]}


def main():
    import io
    import uuid

    import pyarrow as pa
    import pyarrow.parquet as pq

    with tempfile.TemporaryDirectory() as tmp:
        print("ローカル:", local_ops(tmp))
    client = storage.make_client()
    bucket = f"deb-b14-kinds-{uuid.uuid4().hex[:8]}"
    client.create_bucket(Bucket=bucket)
    try:
        print("MinIO   :", object_ops(client, bucket))
        buf = io.BytesIO()
        pq.write_table(pa.table({"n": list(range(1000))}), buf)
        client.put_object(Bucket=bucket, Key="events.parquet", Body=buf.getvalue())
        print("別プロセスで数えた行数:", count_rows_elsewhere(bucket, "events.parquet"))
        try:
            client.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration=load_rules())
        except client.exceptions.ClientError as e:
            print("移行つきの規則:", e.response["Error"]["Code"])
        client.put_bucket_lifecycle_configuration(Bucket=bucket,
                                                  LifecycleConfiguration=without_transitions(load_rules()))
        print("読み戻した規則の ID:", [r["ID"] for r in client.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]])
    finally:
        for o in client.list_objects_v2(Bucket=bucket).get("Contents", []):
            client.delete_object(Bucket=bucket, Key=o["Key"])
        client.delete_bucket(Bucket=bucket)


if __name__ == "__main__":
    main()
