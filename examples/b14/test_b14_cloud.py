"""第 14 章: 設定ファイルの形の検査と、MinIO (S3 互換) を使った boto3 の操作を確かめます。"""
import io
import json
import sys
import uuid
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import requests
import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "etl"))
import etl  # noqa: E402
import small_files  # noqa: E402
import static_checks as sc  # noqa: E402
import storage  # noqa: E402

sys.path.insert(0, str(HERE.parent / "common"))
from neboske_shop import generate  # noqa: E402


@pytest.fixture
def bucket(s3_client):
    name = f"deb-b14-{uuid.uuid4().hex[:12]}"
    s3_client.create_bucket(Bucket=name)
    yield name
    for page in s3_client.get_paginator("list_objects_v2").paginate(Bucket=name):
        for obj in page.get("Contents", []):
            s3_client.delete_object(Bucket=name, Key=obj["Key"])
    s3_client.delete_bucket(Bucket=name)


# ---- 設定ファイルの形 (サービス不要) ----

def test_etl_dockerfile_follows_the_rules():
    text = (HERE / "etl" / "Dockerfile").read_text(encoding="utf-8")
    reqs = (HERE / "etl" / "requirements.txt").read_text(encoding="utf-8")
    assert sc.dockerfile_problems(text, reqs) == []


def test_dockerfile_checker_catches_each_mistake():
    bad = """FROM python
COPY . .
RUN pip install -r requirements.txt
ENV API_KEY=abc123
CMD python etl.py
"""
    problems = sc.dockerfile_problems(bad, "boto3\n")
    for expected in ("タグが無い", "root", "最初の COPY", "--no-cache-dir", "秘密らしい名前",
                     "exec 形式", "バージョン固定"):
        assert any(expected in p for p in problems), expected
    assert any("latest" in p for p in sc.dockerfile_problems("FROM python:latest\nUSER app\n"))


def test_etl_dockerfile_copies_requirements_before_code():
    lines = [ln for ln in (HERE / "etl" / "Dockerfile").read_text(encoding="utf-8").splitlines()
             if ln.startswith(("COPY", "RUN pip"))]
    assert lines[0].startswith("COPY requirements.txt") and lines[1].startswith("RUN pip")
    assert lines[2].startswith("COPY --chown")


def test_compose_example_is_well_formed():
    spec = yaml.safe_load((HERE / "compose.etl.yaml").read_text(encoding="utf-8"))
    assert sc.compose_problems(spec) == []
    assert (HERE / spec["services"]["etl"]["build"] / "Dockerfile").exists()
    assert spec["services"]["etl"]["environment"]["S3_ENDPOINT"] == "http://minio:9000"


def test_compose_checker_catches_mistakes():
    spec = {"services": {
        "db": {"image": "postgres"},
        "app": {"image": "app:1", "depends_on": {"db": {"condition": "service_started"}},
                "environment": {"DB_PASSWORD": "hunter2"}}}}
    problems = sc.compose_problems(spec)
    assert len(problems) == 3


def test_repository_compose_pins_images_and_has_healthchecks():
    spec = yaml.safe_load((HERE.parents[1] / "compose.yaml").read_text(encoding="utf-8"))
    # ローカル学習用なので、パスワードの直書き以外の問題が無いことだけ確かめる
    assert [p for p in sc.compose_problems(spec) if "直書き" not in p] == []
    assert all("healthcheck" in svc for svc in spec["services"].values())


def test_terraform_snippet_shape():
    text = (HERE / "infra" / "main.tf").read_text(encoding="utf-8")
    assert sc.terraform_problems(text) == []
    assert "restrict_public_buckets" in sc.terraform_problems(text.replace("restrict_public_buckets = true", ""))[0]
    assert sc.terraform_problems(text + '\naccess_key = "x"')
    assert sc.terraform_problems(text + "\n}")


def test_iam_policy_is_least_privilege():
    text = (HERE / "iam_read_policy.json").read_text(encoding="utf-8")
    assert sc.policy_problems(text) == []
    wide = json.dumps({"Statement": [{"Sid": "X", "Action": "s3:*", "Resource": "*"}]})
    assert len(sc.policy_problems(wide)) == 2
    wrong = json.dumps({"Statement": [{"Sid": "L", "Action": ["s3:ListBucket"],
                                       "Resource": ["arn:aws:s3:::b/*"]}]})
    assert "ListBucket" in sc.policy_problems(wrong)[0]


def test_make_client_switches_by_environment():
    local = storage.make_client({"S3_ENDPOINT": "http://localhost:9000",
                                 "S3_ACCESS_KEY": "a", "S3_SECRET_KEY": "b"})
    assert local.meta.endpoint_url == "http://localhost:9000"
    aws = storage.make_client({"S3_REGION": "ap-northeast-1"})
    assert aws.meta.endpoint_url == "https://s3.ap-northeast-1.amazonaws.com"


def test_small_files_cost_space_and_hive_partitions_prune(tmp_path):
    stats = small_files.compare(tmp_path / "cmp")
    assert stats["one"]["rows"] == stats["small"]["rows"] == 4040
    assert (stats["one"]["files"], stats["small"]["files"]) == (1, 41)
    assert stats["small"]["bytes"] > 1.5 * stats["one"]["bytes"]
    assert small_files.hive_count(tmp_path / "hive", "2026-03-01") == (24, 180)


# ---- MinIO (S3 互換) を使うテスト ----

def test_put_then_list_sees_the_new_object_at_once(s3_client, bucket):
    s3_client.put_object(Bucket=bucket, Key="a/b.txt", Body=b"hello")
    keys, pages = storage.list_keys(s3_client, bucket, "a/")
    assert keys == ["a/b.txt"] and pages == 1
    assert s3_client.get_object(Bucket=bucket, Key="a/b.txt")["Body"].read() == b"hello"


def test_prefix_is_just_a_string_and_folders_are_a_view(s3_client, bucket):
    for key in ["events/dt=2026-03-01/p.parquet", "events/dt=2026-03-02/p.parquet",
                "events_old/x", "events.csv"]:
        s3_client.put_object(Bucket=bucket, Key=key, Body=b"x")
    keys, _ = storage.list_keys(s3_client, bucket, "events")
    assert len(keys) == 4  # "events/" ではなく "events" で始まる文字列を全部拾う
    keys, _ = storage.list_keys(s3_client, bucket, "events/")
    assert len(keys) == 2
    assert storage.list_folders(s3_client, bucket, "events/") == [
        "events/dt=2026-03-01/", "events/dt=2026-03-02/"]


def test_pagination_costs_one_request_per_page(s3_client, bucket):
    for i in range(25):
        s3_client.put_object(Bucket=bucket, Key=f"k/{i:03d}", Body=b"")
    keys, pages = storage.list_keys(s3_client, bucket, "k/", page_size=10)
    assert len(keys) == 25 and pages == 3
    assert keys == sorted(keys)  # 一覧はキーの辞書順


def test_etl_writes_hive_partitions(s3_client, bucket, tmp_path):
    rows = generate()["events"]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    keys = etl.main({"INPUT_PATH": str(path), "BUCKET": bucket}, client=s3_client)
    assert len(keys) == 180
    assert keys[0] == "events/dt=2026-01-01/part-0000.parquet"
    body = s3_client.get_object(Bucket=bucket, Key="events/dt=2026-03-01/part-0000.parquet")["Body"].read()
    assert pq.read_table(io.BytesIO(body)).num_rows == 24


def test_etl_can_create_the_bucket_for_local_use(s3_client, tmp_path):
    name = f"deb-b14-{uuid.uuid4().hex[:12]}"
    path = tmp_path / "e.jsonl"
    path.write_text(json.dumps(generate()["events"][0]), encoding="utf-8")
    try:
        etl.main({"INPUT_PATH": str(path), "BUCKET": name, "CREATE_BUCKET": "1"}, client=s3_client)
        assert len(storage.list_keys(s3_client, name, "events/")[0]) == 1
    finally:
        for k in storage.list_keys(s3_client, name, "")[0]:
            s3_client.delete_object(Bucket=name, Key=k)
        s3_client.delete_bucket(Bucket=name)


def test_compaction_merges_small_files(s3_client, bucket):
    rows = [r for r in generate()["events"] if r["event_time"].startswith("2026-03-01")]
    storage.write_partitions(s3_client, bucket, "events", rows, rows_per_file=5)
    prefix = "events/dt=2026-03-01/"
    before, _ = storage.list_keys(s3_client, bucket, prefix)
    assert len(before) == 5  # 24 行を 5 行ずつ
    new_key = storage.compact(s3_client, bucket, prefix)
    after, _ = storage.list_keys(s3_client, bucket, prefix)
    assert after == [new_key]
    body = s3_client.get_object(Bucket=bucket, Key=new_key)["Body"].read()
    assert pq.read_table(io.BytesIO(body)).num_rows == 24


def test_large_file_is_uploaded_in_parts(s3_client, bucket, tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (11 * storage.MIB))
    etag = storage.upload_large(s3_client, bucket, "big.bin", big)
    assert etag.endswith("-3")  # 5 MiB ずつ 3 パート
    s3_client.put_object(Bucket=bucket, Key="small.bin", Body=b"x")
    assert "-" not in s3_client.head_object(Bucket=bucket, Key="small.bin")["ETag"]


def test_presigned_url_gives_temporary_access(s3_client, bucket):
    s3_client.put_object(Bucket=bucket, Key="report.csv", Body=b"a,b\n1,2\n")
    url = storage.presigned_get(s3_client, bucket, "report.csv", seconds=60)
    assert requests.get(url, timeout=10).text == "a,b\n1,2\n"
    assert requests.get(url.replace("report.csv", "other.csv"), timeout=10).status_code == 403
    expired = storage.presigned_get(s3_client, bucket, "report.csv", seconds=1)
    import time
    time.sleep(2.5)
    assert requests.get(expired, timeout=10).status_code == 403


def test_lifecycle_rule_roundtrip(s3_client, bucket):
    storage.expire_prefix_after(s3_client, bucket, "tmp/", days=7)
    rules = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
    assert rules[0]["Expiration"]["Days"] == 7
    assert rules[0]["Status"] == "Enabled"
    assert (rules[0].get("Filter") or {}).get("Prefix", rules[0].get("Prefix")) == "tmp/"


def test_local_minio_hides_a_key_that_is_also_a_folder(s3_client, bucket):
    # S3 では "events" と "events/…" は別のキーとして両方置ける。この本の MinIO (旧版・1 ドライブ) は
    # ファイルシステムに置くため、両方は見えなくなる。ローカルと本番の差の実例。
    keys = ["events/dt=1/p", "events"]
    try:
        for key in keys:
            s3_client.put_object(Bucket=bucket, Key=key, Body=b"x")
        assert len(storage.list_keys(s3_client, bucket, "")[0]) < 2
    finally:
        for key in keys:
            s3_client.delete_object(Bucket=bucket, Key=key)


def test_demo_output(s3_client, bucket, capsys):
    import demo_storage
    demo_storage.demo(s3_client, bucket)
    out = capsys.readouterr().out
    assert "置いたキー数: " in out and "dt=2026-01-02/compacted.parquet" in out


def test_policy_checker_flags_getobject_on_bucket_only():
    wrong = json.dumps({"Statement": [{"Sid": "G", "Action": "s3:GetObject",
                                       "Resource": "arn:aws:s3:::deb-lake"}]})
    assert "GetObject" in sc.policy_problems(wrong)[0]


def test_prefix_match_is_character_by_character(s3_client, bucket):
    for day in ["2026-01-01", "2026-01-02", "2026-01-10"]:
        s3_client.put_object(Bucket=bucket, Key=f"events/dt={day}/p", Body=b"x")
    keys, _ = storage.list_keys(s3_client, bucket, "events/dt=2026-01-0")
    assert keys == ["events/dt=2026-01-01/p", "events/dt=2026-01-02/p"]  # 10 日は入らない
