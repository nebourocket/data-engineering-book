"""章のコード例（examples/）で使う共通フィクスチャ。

外部サービスは環境変数で場所を教えます（compose.yaml の値は README を参照）。
  PG_DSN           例: postgresql://deb:deb@localhost:5432/deb
  S3_ENDPOINT      例: http://localhost:9000（S3_ACCESS_KEY / S3_SECRET_KEY も使います）
  KAFKA_BOOTSTRAP  例: localhost:19092
未設定なら skip します。DE_BOOK_REQUIRE_SERVICES=1 のとき（CI）は skip ではなく fail にします。
"""
import os

import pytest


def _require(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if not missing:
        return
    message = f"環境変数 {', '.join(missing)} が未設定です（docker compose up -d と README を参照）"
    if os.environ.get("DE_BOOK_REQUIRE_SERVICES") == "1":
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture
def pg_dsn():
    _require("PG_DSN")
    return os.environ["PG_DSN"]


@pytest.fixture
def s3_client():
    _require("S3_ENDPOINT")
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
        region_name="us-east-1",
    )


@pytest.fixture
def kafka_bootstrap():
    _require("KAFKA_BOOTSTRAP")
    return os.environ["KAFKA_BOOTSTRAP"]
