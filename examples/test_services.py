"""compose.yaml のサービスにつながることの確認（フィクスチャの動作確認を兼ねます）。"""
import uuid


def test_postgres(pg_dsn):
    import psycopg

    with psycopg.connect(pg_dsn) as con:
        assert con.execute("select 1").fetchone() == (1,)


def test_minio(s3_client):
    bucket = f"smoke-{uuid.uuid4().hex[:8]}"
    s3_client.create_bucket(Bucket=bucket)
    s3_client.put_object(Bucket=bucket, Key="a.txt", Body=b"hello")
    assert s3_client.get_object(Bucket=bucket, Key="a.txt")["Body"].read() == b"hello"
    s3_client.delete_object(Bucket=bucket, Key="a.txt")
    s3_client.delete_bucket(Bucket=bucket)


def test_redpanda(kafka_bootstrap):
    from confluent_kafka.admin import AdminClient

    meta = AdminClient({"bootstrap.servers": kafka_bootstrap}).list_topics(timeout=10)
    assert len(meta.brokers) >= 1
