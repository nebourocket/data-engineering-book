"""4 章の ETL スクリプトのテスト。本文の説明どおりに動くことを確かめます。"""
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for path in (str(ROOT), str(HERE)):  # examples.common と neboske_etl を import できるようにする
    if path not in sys.path:
        sys.path.insert(0, path)

from make_sample import write_sample_csv  # noqa: E402
from neboske_etl import retry as retry_module  # noqa: E402
from neboske_etl.config import Settings  # noqa: E402
from neboske_etl.models import Order, ValidationError  # noqa: E402
from neboske_etl.pipeline import run, upload  # noqa: E402
from neboske_etl.reader import iter_rows  # noqa: E402
from neboske_etl.retry import retry  # noqa: E402
from neboske_etl.validate import parse_order  # noqa: E402

GOOD_ROW = {"order_id": "1", "customer_id": "10", "ordered_at": "2026-01-01 09:00:00",
            "status": "shipped", "item_count": "2", "total_amount": "3400"}


@pytest.fixture(scope="module")
def sample_csv(tmp_path_factory):
    path = tmp_path_factory.mktemp("input") / "orders.csv"
    assert write_sample_csv(path) == 3000
    return path


def make_settings(csv_path, out_dir, **kw):
    return Settings(input_path=csv_path, output_dir=out_dir, **kw)


# --- 検証 -------------------------------------------------------------------

def test_parse_order_returns_typed_order():
    order = parse_order(GOOD_ROW)
    assert order == Order(1, 10, datetime(2026, 1, 1, 9, 0), "shipped", 2, 3400)


def test_status_case_is_normalized():
    assert parse_order({**GOOD_ROW, "status": " SHIPPED "}).status == "shipped"


@pytest.mark.parametrize("field,value,reason", [
    ("order_id", "abc", "整数ではありません"),
    ("order_id", "0", "1 以上"),
    ("total_amount", "-500", "0 以上"),
    ("ordered_at", "2026-13-45", "日時として読めません"),
    ("status", "returned", "知らない値"),
    ("customer_id", "", "整数ではありません"),
])
def test_parse_order_rejects_bad_values(field, value, reason):
    with pytest.raises(ValidationError) as info:
        parse_order({**GOOD_ROW, field: value})
    assert info.value.field == field
    assert reason in info.value.reason


def test_validation_error_is_value_error():
    assert issubclass(ValidationError, ValueError)


def test_order_is_immutable():
    order = parse_order(GOOD_ROW)
    with pytest.raises(AttributeError):
        order.status = "placed"


# --- 読み込み ---------------------------------------------------------------

def test_iter_rows_is_lazy_generator(sample_csv):
    rows = iter_rows(sample_csv)
    assert type(rows).__name__ == "generator"
    assert next(rows)["order_id"] == "1"


def test_iter_rows_rejects_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("order_id,status\n1,placed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="必要な列がありません"):
        list(iter_rows(path))


# --- パイプライン -----------------------------------------------------------

def test_run_splits_good_and_bad_rows(sample_csv, tmp_path):
    result = run(make_settings(sample_csv, tmp_path / "out"))
    assert (result.read, result.written, result.rejected) == (3000, 2996, 4)
    table = pq.read_table(result.parquet_path)
    assert table.num_rows == 2996
    assert str(table.schema.field("ordered_at").type) == "timestamp[ms]"
    assert set(table.column("status").to_pylist()) <= {"placed", "shipped", "delivered", "cancelled"}
    assert min(table.column("total_amount").to_pylist()) >= 0
    rejects = result.rejects_path.read_text(encoding="utf-8").splitlines()
    assert len(rejects) == 1 + 4
    assert rejects[0].endswith(",error")
    assert any("total_amount" in line for line in rejects[1:])


def test_batch_size_does_not_change_result(sample_csv, tmp_path):
    big = run(make_settings(sample_csv, tmp_path / "a", batch_size=1000))
    small = run(make_settings(sample_csv, tmp_path / "b", batch_size=7))
    assert pq.read_table(big.parquet_path).equals(pq.read_table(small.parquet_path))


def test_run_is_idempotent_and_leaves_no_temp_file(sample_csv, tmp_path):
    settings = make_settings(sample_csv, tmp_path / "out")
    first = run(settings)
    second = run(settings)
    assert pq.read_table(first.parquet_path).num_rows == pq.read_table(second.parquet_path).num_rows
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["orders.parquet", "orders.rejects.csv"]


def test_failure_leaves_no_parquet(tmp_path):
    bad = tmp_path / "orders.csv"
    bad.write_text("order_id,status\n1,placed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run(make_settings(bad, tmp_path / "out"))
    assert not (tmp_path / "out" / "orders.parquet").exists()
    assert not list((tmp_path / "out").glob("*.tmp"))


def test_clean_data_has_no_rejects(tmp_path):
    clean = tmp_path / "orders.csv"
    write_sample_csv(clean, defects=False)
    result = run(make_settings(clean, tmp_path / "out"))
    assert result.rejected == 0 and result.written == 3000


# --- 再試行 -----------------------------------------------------------------

@pytest.fixture
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(retry_module.time, "sleep", waits.append)
    return waits


def test_retry_succeeds_after_transient_failures(no_sleep):
    calls = []

    @retry(attempts=3, wait=1.0)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise OSError("一時的な失敗")
        return "ok"

    assert flaky() == "ok"
    assert no_sleep == [1.0, 2.0]  # 待ち時間は倍になる


def test_retry_gives_up_and_reraises(no_sleep):
    @retry(attempts=2, wait=0.5)
    def always_fails():
        raise OSError("ずっと失敗")

    with pytest.raises(OSError, match="ずっと失敗"):
        always_fails()
    assert no_sleep == [0.5]


def test_retry_does_not_retry_other_exceptions(no_sleep):
    calls = []

    @retry(attempts=3)
    def bug():
        calls.append(1)
        raise KeyError("バグ")

    with pytest.raises(KeyError):
        bug()
    assert len(calls) == 1 and no_sleep == []


# --- 設定 -------------------------------------------------------------------

def test_settings_from_env_uses_defaults():
    settings = Settings.from_env({"ETL_INPUT": "in.csv", "ETL_OUTPUT_DIR": "out"})
    assert settings.batch_size == 1000
    assert settings.max_reject_ratio == 0.05
    assert settings.input_path == Path("in.csv")


def test_settings_missing_required_variable_fails_fast():
    with pytest.raises(KeyError, match="ETL_INPUT"):
        Settings.from_env({"ETL_OUTPUT_DIR": "out"})


def test_secret_is_not_in_repr():
    settings = Settings.from_env({"ETL_INPUT": "i", "ETL_OUTPUT_DIR": "o", "S3_SECRET_KEY": "dummy-secret-xyz"})
    assert "dummy-secret-xyz" not in repr(settings)
    assert settings.s3_secret_key == "dummy-secret-xyz"


# --- コマンドとして ---------------------------------------------------------

def run_cli(sample_csv, out_dir, **env):
    full_env = {**os.environ, "ETL_INPUT": str(sample_csv), "ETL_OUTPUT_DIR": str(out_dir),
                "PYTHONPATH": str(ROOT), **env}
    return subprocess.run([sys.executable, "-m", "neboske_etl"], cwd=HERE, env=full_env,
                          capture_output=True, text=True, check=False)


def test_cli_success_logs_to_stderr(sample_csv, tmp_path):
    result = run_cli(sample_csv, tmp_path / "out")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert re.search(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} INFO neboske_etl.pipeline 完了: "
                     r"読み込み 3000 行、書き込み 2996 行、除外 4 行$", result.stderr, re.M)


def test_cli_fails_when_too_many_rejects(sample_csv, tmp_path):
    result = run_cli(sample_csv, tmp_path / "out", ETL_MAX_REJECT_RATIO="0.0001")
    assert result.returncode == 1
    assert "除外が多すぎます" in result.stderr


def test_cli_debug_level_shows_each_rejected_row(sample_csv, tmp_path):
    quiet = run_cli(sample_csv, tmp_path / "a")
    debug = run_cli(sample_csv, tmp_path / "b", LOG_LEVEL="DEBUG")
    assert "行を除外" not in quiet.stderr
    assert debug.stderr.count("行を除外") == 4


def test_cli_without_settings_fails(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("ETL_INPUT", "ETL_OUTPUT_DIR")}
    result = subprocess.run([sys.executable, "-m", "neboske_etl"], cwd=HERE, env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "KeyError" in result.stderr


# --- 本文に写した出力 -------------------------------------------------------

def run_script(name, cwd=HERE):
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, str(HERE / name)], cwd=cwd, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)


def test_generator_demo_output():
    assert run_script("generator_demo.py").stdout == "generator\n1\n2\n['3']\n"


def test_logging_demo_output():
    lines = run_script("logging_demo.py").stdout.splitlines()
    assert lines[:3] == [
        "INFO neboske_etl.demo 読み込み 3000 行",
        "WARNING neboske_etl.demo 除外 4 行",
        "ERROR neboske_etl.demo 整数に直せない値がありました",
    ]
    assert lines[3] == "Traceback (most recent call last):"


def test_naive_script_fails_without_context(sample_csv, tmp_path):
    (tmp_path / "orders.csv").write_bytes(sample_csv.read_bytes())
    # 最初の版は "SHIPPED" を数え落とすが、エラーにもならない
    assert any(row["status"] == "SHIPPED" for row in iter_rows(sample_csv))
    result = run_script("step1_naive.py", cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout.endswith("ValueError: invalid literal for int() with base 10: 'abc'\n")


@pytest.mark.parametrize("name", ["setup_env.sh", "run_etl.sh", "run_tests.sh"])
def test_scripts_parse(name):
    assert subprocess.run(["bash", "-n", str(HERE / name)]).returncode == 0


def normalize(text):
    """ログの時刻だけを伏せます（実行のたびに変わるため）。"""
    return re.sub(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} ", "<時刻> ", text, flags=re.M)


def test_run_etl_script_matches_book(tmp_path):
    result = subprocess.run(["bash", str(HERE / "run_etl.sh")], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, check=False)
    assert result.returncode == 0, result.stdout
    expected = (HERE / "expected" / "run_etl.txt").read_text(encoding="utf-8")
    assert normalize(result.stdout) == normalize(expected)


def test_requirements_pin_exact_versions():
    lines = (HERE / "requirements.txt").read_text(encoding="utf-8").split()
    assert lines and all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", ln) for ln in lines)


def test_upload_retries_connection_errors(sample_csv, tmp_path, no_sleep):
    from botocore.exceptions import EndpointConnectionError

    result = run(make_settings(sample_csv, tmp_path / "out"))
    settings = make_settings(sample_csv, tmp_path / "out", s3_bucket="nowhere",
                             s3_endpoint="http://127.0.0.1:1", s3_access_key="x", s3_secret_key="y")
    with pytest.raises(EndpointConnectionError):
        upload(settings, result.parquet_path)
    assert no_sleep == [1.0, 2.0]  # 3 回試して、2 回待った


# --- サービスを使う ---------------------------------------------------------

def test_upload_puts_parquet_into_minio(sample_csv, tmp_path, s3_client):
    result = run(make_settings(sample_csv, tmp_path / "out"))
    bucket = f"b04-{uuid.uuid4().hex[:8]}"
    s3_client.create_bucket(Bucket=bucket)
    try:
        settings = make_settings(
            sample_csv, tmp_path / "out", s3_bucket=bucket, s3_endpoint=os.environ["S3_ENDPOINT"],
            s3_access_key=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
            s3_secret_key=os.environ.get("S3_SECRET_KEY", "minioadmin"))
        upload(settings, result.parquet_path)
        body = s3_client.get_object(Bucket=bucket, Key="orders/orders.parquet")["Body"].read()
        assert body == result.parquet_path.read_bytes()
    finally:
        s3_client.delete_object(Bucket=bucket, Key="orders/orders.parquet")
        s3_client.delete_bucket(Bucket=bucket)
