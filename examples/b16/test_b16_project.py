"""第 16 章の通しのパイプラインのテスト。手元のフォルダ (LocalS3) と MinIO の両方で動かします。"""
import sys
import uuid
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.b16 import ingest, quality  # noqa: E402
from examples.b16.pipeline import make_client, run  # noqa: E402
from examples.b16.store import LocalS3  # noqa: E402

DT = "2026-07-01"
BUCKET = "neboske-lake"


@pytest.fixture
def local(tmp_path):
    s3 = LocalS3(tmp_path / "landing")
    s3.create_bucket(Bucket=BUCKET)
    return s3


def results(workdir, dt=DT):
    con = duckdb.connect(str(Path(workdir) / "warehouse.duckdb"), read_only=True)
    try:
        return con.execute(
            "SELECT check_name, severity, passed FROM dq_results WHERE run_dt = ? ORDER BY rowid", [dt]).fetchall()
    finally:
        con.close()


def mart(workdir):
    con = duckdb.connect(str(Path(workdir) / "warehouse.duckdb"), read_only=True)
    try:
        return con.execute("SELECT count(*), sum(sales) FROM analytics.fct_daily_sales").fetchone()
    finally:
        con.close()


def test_pipeline_end_to_end_with_local_store(tmp_path, local):
    figure = run(local, BUCKET, DT, tmp_path)
    assert figure.read_text(encoding="utf-8").lstrip().startswith(("<?xml", "<svg"))
    outcome = results(tmp_path)
    assert len(outcome) == len(quality.CHECKS)
    assert {name for name, severity, passed in outcome if not passed} == {"events の event_id が重複していない"}
    assert all(severity == "warn" for _, severity, passed in outcome if not passed)  # 落ちたのは warn だけ
    # 第 10 章の mart と同じ定義: キャンセルを除いた日別売上
    con = duckdb.connect(str(tmp_path / "warehouse.duckdb"), read_only=True)
    assert con.execute("SELECT sum(sales) FROM analytics.fct_daily_sales").fetchone() == con.execute(
        "SELECT sum(order_amount) FROM analytics.fct_orders WHERE status <> 'cancelled'").fetchone()
    assert con.execute("SELECT count(*) FROM main.events").fetchone() == (4040,)  # 重複も raw にはそのまま
    con.close()


def test_rerun_gives_same_result(tmp_path, local):
    run(local, BUCKET, DT, tmp_path)
    first = (mart(tmp_path), results(tmp_path))
    run(local, BUCKET, DT, tmp_path)
    assert (mart(tmp_path), results(tmp_path)) == first  # 冪等: dq_results も 2 組にならない


class Recording(LocalS3):
    """put と delete の呼び出し順を記録します。fail_on に入れたキーの put で失敗させます。"""

    def __init__(self, root, fail_on=()):
        super().__init__(root)
        self.calls, self.fail_on = [], set(fail_on)

    def put_object(self, Bucket, Key, Body):
        if Key in self.fail_on:
            raise OSError("置いている途中で落ちた")
        self.calls.append(("put", Key))
        super().put_object(Bucket, Key, Body)

    def delete_object(self, Bucket, Key):
        self.calls.append(("delete", Key))
        super().delete_object(Bucket, Key)


def test_land_removes_old_marker_first_and_puts_new_one_last(tmp_path):
    s3 = Recording(tmp_path)
    ingest.land(s3, BUCKET, DT)
    marker = f"raw/dt={DT}/_SUCCESS"
    assert s3.calls[0] == ("delete", marker)
    assert s3.calls[-1] == ("put", marker)
    assert all(call != ("put", marker) for call in s3.calls[:-1])  # 印を置くのは最後の 1 回だけ


def test_interrupted_reland_leaves_no_marker_and_load_refuses(tmp_path):
    ingest.land(LocalS3(tmp_path), BUCKET, DT)  # 1 回目は成功 (印がある)
    s3 = Recording(tmp_path, fail_on={f"raw/dt={DT}/order_items.parquet"})
    with pytest.raises(OSError):
        ingest.land(s3, BUCKET, DT)  # 2 回目は途中で落ちる
    with pytest.raises(RuntimeError, match="_SUCCESS"):
        ingest.load_raw(duckdb.connect(), s3, BUCKET, DT)  # 古い印が残っていないので、読めない


def test_load_refuses_partition_without_success_marker(local):
    ingest.land(local, BUCKET, DT)
    local.delete_object(Bucket=BUCKET, Key=f"raw/dt={DT}/_SUCCESS")
    with pytest.raises(RuntimeError, match="_SUCCESS"):
        ingest.load_raw(duckdb.connect(), local, BUCKET, DT)


def test_error_check_stops_before_figure():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA analytics")
    con.execute("CREATE TABLE main.orders AS SELECT 1 AS order_id, 'placed' AS status")
    con.execute("CREATE TABLE analytics.fct_daily_sales AS SELECT DATE '2026-01-01' AS order_date, 100 AS sales")
    con.execute("CREATE TABLE main.order_items AS SELECT 1 AS order_id, 1 AS quantity, 90 AS unit_price")  # 合計が合わない
    con.execute("CREATE TABLE main.events AS SELECT 1 AS event_id, '2026-01-01 00:00:00' AS event_time, "
                "'2026-01-01 00:00:05' AS received_at")
    with pytest.raises(quality.QualityError, match="一致する"):
        quality.run_checks(con, DT)
    # 止まる前に、全部の結果が記録されている
    assert con.execute("SELECT count(*) FROM dq_results").fetchone() == (len(quality.CHECKS),)


def test_null_date_is_counted_once():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA analytics")
    con.execute("CREATE TABLE analytics.fct_daily_sales AS SELECT * FROM (VALUES (DATE '2026-01-01', 1), (NULL, 2)) t(order_date, sales)")
    bad, total = con.execute(quality.CHECKS[1].sql).fetchone()
    assert (bad, total) == (1, 2)  # NULL の行は 1 回だけ数える


def test_pipeline_with_minio(tmp_path, s3_client):  # s3_client があると S3_ENDPOINT の設定が確かめられる
    bucket = f"b16-{uuid.uuid4().hex[:8]}"
    client = make_client(tmp_path, bucket)
    try:
        run(client, bucket, DT, tmp_path)
        keys = {o["Key"] for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
                for o in page["Contents"]}
        assert f"raw/dt={DT}/_SUCCESS" in keys and f"raw/dt={DT}/orders.parquet" in keys
        assert any(k.startswith("landing/events/dt=") and k.endswith("/_SUCCESS") for k in keys)
        assert mart(tmp_path)[0] > 0
    finally:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for o in page.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=o["Key"])
        client.delete_bucket(Bucket=bucket)


def test_interview_queries_run(tmp_path, local):
    run(local, BUCKET, DT, tmp_path)
    con = duckdb.connect(str(tmp_path / "warehouse.duckdb"), read_only=True)
    statements = [s.strip() for s in (Path(__file__).parent / "interview.sql").read_text(encoding="utf-8").split(";")]
    outputs = [con.execute(s).fetchall() for s in statements if "SELECT" in s]
    assert len(outputs) == 3
    first_orders, moving, check = outputs
    assert len({r[0] for r in first_orders}) == len(first_orders)  # 顧客ごとに 1 行
    assert len(moving) == mart(tmp_path)[0]
    assert check == [(3000, 3000)]  # 全注文に明細がある
