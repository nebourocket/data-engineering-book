"""章のコード例（examples/）で使う共通フィクスチャ。

外部サービスは環境変数で場所を教えます（compose.yaml の値は README を参照）。
  PG_DSN           例: postgresql://deb:deb@localhost:5432/deb
  S3_ENDPOINT      例: http://localhost:9000（S3_ACCESS_KEY / S3_SECRET_KEY も使います）
  KAFKA_BOOTSTRAP  例: localhost:19092
未設定なら skip します。DE_BOOK_REQUIRE_SERVICES=1 のとき（CI）は skip ではなく fail にします。
"""
import importlib.util
import os
import shutil

import pytest

# 応用編 (a01〜a03) は追加の道具が要ります。無いときは収集ごと飛ばし、既定の pytest を緑に保ちます。
# 動かし方は README の「Advanced examples」を参照してください。
ADVANCED_REQUIRES = {
    "a01": ["pyspark", "pandas"],
    "a02": ["pyspark", "pandas"],
    "a03": ["deltalake", "pyiceberg"],
}
NEEDS_JAVA = {"a01", "a02"}


def pytest_ignore_collect(collection_path, config):
    name = next((p for p in collection_path.parts if p in ADVANCED_REQUIRES), None)
    if name is None:
        return None
    missing = [m for m in ADVANCED_REQUIRES[name] if importlib.util.find_spec(m) is None]
    if name in NEEDS_JAVA and shutil.which("java") is None:
        missing.append("java")
    return True if missing else None


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


@pytest.fixture(scope="session")
def spark():
    """ローカルの SparkSession (応用編 a01・a02 用)。パーティション数を小さくして、UI は切ります。"""
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[2]")
        .appName("de-book-advanced")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.default.parallelism", "4")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )
    yield session
    session.stop()
