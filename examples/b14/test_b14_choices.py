"""第14章の「どこで何を動かすか」「保存の種類と保持期間」の節の数字と挙動を確かめます。"""
import io
import json
import shutil
import sys
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import measure_start as ms  # noqa: E402
import storage_kinds as sk  # noqa: E402


@pytest.fixture
def parquet_file(tmp_path):
    path = tmp_path / "events.parquet"
    pq.write_table(pa.table({"n": list(range(1000))}), path)
    return path


@pytest.fixture
def bucket(s3_client):
    name = f"deb-b14-kinds-{uuid.uuid4().hex[:10]}"
    s3_client.create_bucket(Bucket=name)
    yield name
    for o in s3_client.list_objects_v2(Bucket=name).get("Contents", []):
        s3_client.delete_object(Bucket=name, Key=o["Key"])
    s3_client.delete_bucket(Bucket=name)


# ---- 起動の遅さ (本文は「10 倍を超える」とだけ書く) ----

def test_new_process_is_over_10x_slower_than_warm_call(parquet_file):
    assert ms.new_process_ms(parquet_file) > 10 * ms.warm_ms(parquet_file)


def test_new_container_is_over_10x_slower_than_warm_call(parquet_file):
    if not shutil.which("docker"):
        pytest.skip("docker が無い環境では測りません")
    took = ms.new_container_ms(parquet_file)
    if took is None:
        pytest.skip("画像 de-book-dev が無い、または docker を使えません")
    assert took > 10 * ms.warm_ms(parquet_file)


# ---- ファイルとオブジェクトの違い ----

def test_local_append_keeps_the_same_file_and_rename_moves_the_name(tmp_path):
    got = sk.local_ops(tmp_path)
    assert got == {"追記後のバイト数": 6, "追記しても同じファイルか": True, "改名後に旧名が残るか": False}


def test_object_has_no_append_and_rename_is_copy_then_delete(s3_client, bucket):
    got = sk.object_ops(s3_client, bucket)
    assert got["追記後のバイト数"] == 6
    assert got["追記で ETag が変わったか"] is True
    assert got["コピー直後のキー"] == ["log-new.txt", "log.txt"]
    assert got["改名後のキー"] == ["log-new.txt"]


def test_new_process_can_read_what_an_earlier_one_left_in_storage(s3_client, bucket):
    buf = io.BytesIO()
    pq.write_table(pa.table({"n": list(range(1000))}), buf)
    s3_client.put_object(Bucket=bucket, Key="events.parquet", Body=buf.getvalue())
    assert sk.count_rows_elsewhere(bucket, "events.parquet") == 1000


# ---- ライフサイクル規則 ----

def test_lifecycle_json_has_transition_and_expiration():
    rules = {r["ID"]: r for r in sk.load_rules()["Rules"]}
    assert rules["events-to-cold-then-expire"]["Transitions"] == [{"Days": 30, "StorageClass": "STANDARD_IA"}]
    assert rules["events-to-cold-then-expire"]["Expiration"] == {"Days": 365}
    assert rules["tmp-expire-fast"]["Expiration"] == {"Days": 1}


def test_minio_rejects_transition_but_accepts_expiration_only_rules(s3_client, bucket):
    with pytest.raises(s3_client.exceptions.ClientError) as e:
        s3_client.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration=sk.load_rules())
    assert e.value.response["Error"]["Code"] == "InvalidStorageClass"
    s3_client.put_bucket_lifecycle_configuration(
        Bucket=bucket, LifecycleConfiguration=sk.without_transitions(sk.load_rules()))
    got = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
    assert [r["ID"] for r in got] == ["events-to-cold-then-expire", "tmp-expire-fast"]
    assert json.dumps(got)  # 読み戻せる
