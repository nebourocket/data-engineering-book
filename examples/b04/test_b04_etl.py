"""4 章の ETL スクリプトのテスト。本文の説明どおりに動くことを確かめます。"""
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pyarrow.parquet as pq
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for path in (str(ROOT), str(HERE)):  # examples.common と neboske_etl を import できるようにする
    if path not in sys.path:
        sys.path.insert(0, path)

from make_sample import write_sample_csv  # noqa: E402
from neboske_etl.config import Settings  # noqa: E402
from neboske_etl.models import Order, ValidationError  # noqa: E402
from neboske_etl.fetch import TransientError, fetch_json  # noqa: E402
from neboske_etl.pipeline import TooManyRejects, run, upload  # noqa: E402
from neboske_etl.reader import iter_rows  # noqa: E402
from neboske_etl.retry import call_with_retry  # noqa: E402
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
    assert order == Order(1, 10, datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), "shipped", 2, 3400)  # 9 時 (JST) は 0 時 (UTC)


def test_status_case_is_normalized():
    assert parse_order({**GOOD_ROW, "status": " SHIPPED "}).status == "shipped"


@pytest.mark.parametrize("field,value,reason", [
    ("order_id", "abc", "整数ではありません"),
    ("order_id", "0", "1 以上"),
    ("total_amount", "-500", "0 以上"),
    ("ordered_at", "2026-13-45", "日時として読めません"),
    ("ordered_at", "0001-01-01 00:00:00", "日時として読めません"),  # UTC に直すと範囲外
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
    assert str(table.schema.field("ordered_at").type) == "timestamp[ms, tz=UTC]"
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
    assert pq.read_table(first.parquet_path).equals(pq.read_table(second.parquet_path))
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["orders.parquet", "orders.rejects.csv"]


def test_failure_leaves_no_parquet(tmp_path):
    bad = tmp_path / "orders.csv"
    bad.write_text("order_id,status\n1,placed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run(make_settings(bad, tmp_path / "out"))
    assert not (tmp_path / "out" / "orders.parquet").exists()
    assert not list((tmp_path / "out").glob("*.tmp"))


def test_header_error_keeps_previous_outputs(sample_csv, tmp_path):
    out = tmp_path / "out"
    run(make_settings(sample_csv, out))
    before = (out / "orders.rejects.csv").read_bytes()
    broken = tmp_path / "orders.csv"
    broken.write_text("order_id,status\n1,placed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run(make_settings(broken, out))
    assert (out / "orders.rejects.csv").read_bytes() == before  # 前回の記録を壊さない
    assert (out / "orders.parquet").exists()


def test_too_many_rejects_publishes_no_parquet(sample_csv, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(TooManyRejects, match="0.13%"):
        run(make_settings(sample_csv, out, max_reject_ratio=0.0001))
    assert not (out / "orders.parquet").exists()  # 公開しない
    assert (out / "orders.rejects.csv").exists()  # 原因調査のために記録は残す
    assert not list(out.glob("*.tmp"))


def test_clean_data_has_no_rejects(tmp_path):
    clean = tmp_path / "orders.csv"
    write_sample_csv(clean, defects=False)
    result = run(make_settings(clean, tmp_path / "out"))
    assert result.rejected == 0 and result.written == 3000


# --- 再試行 -----------------------------------------------------------------

def test_retry_succeeds_after_transient_failures():
    calls, waits = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("一時的な失敗")
        return "ok"

    assert call_with_retry(flaky, attempts=3, wait=1.0, sleep=waits.append) == "ok"
    assert len(waits) == 2
    assert 0 <= waits[0] <= 1.0 and 0 <= waits[1] <= 2.0  # 上限は倍になり、実際の待ちは乱数


def test_retry_gives_up_and_reraises():
    waits = []

    def always_fails():
        raise TimeoutError("ずっと失敗")

    with pytest.raises(TimeoutError, match="ずっと失敗"):
        call_with_retry(always_fails, attempts=2, sleep=waits.append)
    assert len(waits) == 1


@pytest.mark.parametrize("error", [PermissionError("権限が無い"), FileNotFoundError("無い"), KeyError("バグ")])
def test_retry_does_not_retry_permanent_errors(error):
    calls, waits = [], []

    def broken():
        calls.append(1)
        raise error

    with pytest.raises(type(error)):
        call_with_retry(broken, attempts=3, sleep=waits.append)
    assert len(calls) == 1 and waits == []


class FlakyServer:
    """最初の数回は 500 を返し、そのあと JSON を返す小さな HTTP サーバ。"""

    def __init__(self, failures, truncated=0):
        outer = self
        outer.failures, outer.truncated, outer.hits = failures, truncated, 0

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits += 1
                if self.path == "/missing":
                    self.send_response(404)
                    self.end_headers()
                elif outer.hits <= outer.truncated:  # 本文が途中で切れる
                    self.send_response(200)
                    self.send_header("Content-Length", "100")
                    self.end_headers()
                    self.wfile.write(b'{"rate"')
                elif outer.hits <= outer.failures:
                    self.send_response(500)
                    self.end_headers()
                else:
                    body = b'{"rate": 150}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def test_fetch_json_retries_server_errors():
    server = FlakyServer(failures=2)
    try:
        waits = []
        assert fetch_json(server.url + "/rate", sleep=waits.append) == {"rate": 150}
        assert server.hits == 3 and len(waits) == 2
    finally:
        server.close()


def test_fetch_json_retries_truncated_body():
    server = FlakyServer(failures=0, truncated=2)
    try:
        waits = []
        assert fetch_json(server.url + "/rate", sleep=waits.append) == {"rate": 150}
        assert server.hits == 3 and len(waits) == 2
    finally:
        server.close()


def test_fetch_json_does_not_retry_404():
    import urllib.error

    server = FlakyServer(failures=0)
    try:
        waits = []
        with pytest.raises(urllib.error.HTTPError):
            fetch_json(server.url + "/missing", sleep=waits.append)
        assert server.hits == 1 and waits == []
    finally:
        server.close()


def test_fetch_json_gives_up_after_attempts():
    server = FlakyServer(failures=99)
    try:
        with pytest.raises(TransientError, match="HTTP 500"):
            fetch_json(server.url + "/rate", attempts=3, sleep=lambda _: None)
        assert server.hits == 3
    finally:
        server.close()


# --- 設定 -------------------------------------------------------------------

def test_settings_from_env_uses_defaults():
    settings = Settings.from_env({"ETL_INPUT": "in.csv", "ETL_OUTPUT_DIR": "out"})
    assert settings.batch_size == 1000
    assert settings.max_reject_ratio == 0.05
    assert settings.input_path == Path("in.csv")


def test_settings_missing_required_variable_fails_fast():
    with pytest.raises(KeyError, match="ETL_INPUT"):
        Settings.from_env({"ETL_OUTPUT_DIR": "out"})


def test_log_level_is_case_insensitive():
    assert Settings.from_env({"ETL_INPUT": "i", "ETL_OUTPUT_DIR": "o", "LOG_LEVEL": "debug"}).log_level == "DEBUG"


def test_bad_number_names_the_variable():
    with pytest.raises(ValueError, match="ETL_BATCH_SIZE"):
        Settings.from_env({"ETL_INPUT": "i", "ETL_OUTPUT_DIR": "o", "ETL_BATCH_SIZE": "たくさん"})


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
    assert "除外が多すぎます: 0.13% (上限 0.01%)" in result.stderr
    assert not (tmp_path / "out" / "orders.parquet").exists()


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
    lines = [ln for name in ("requirements.txt", "requirements-dev.txt")
             for ln in (HERE / name).read_text(encoding="utf-8").splitlines() if not ln.startswith("-r ")]
    assert lines and all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", ln) for ln in lines)


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
