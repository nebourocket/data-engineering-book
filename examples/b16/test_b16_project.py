"""第 16 章の通しのパイプラインのテスト。DirStore (サービスなし) と MinIO の両方で動かします。"""
import sys
import uuid
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.b16 import ingest, quality  # noqa: E402
from examples.b16.pipeline import run  # noqa: E402
from examples.b16.store import DirStore, S3Store  # noqa: E402

DT = "2026-07-01"


def results(workdir, dt=DT):
    con = duckdb.connect(str(Path(workdir) / "warehouse.duckdb"), read_only=True)
    try:
        return con.execute(
            "SELECT check_name, severity, passed FROM dq_results WHERE run_dt = ? ORDER BY rowid", [dt]).fetchall()
    finally:
        con.close()


def sales_total(workdir):
    con = duckdb.connect(str(Path(workdir) / "warehouse.duckdb"), read_only=True)
    try:
        return con.execute("SELECT count(*), sum(sales) FROM analytics.fct_daily_sales").fetchone()
    finally:
        con.close()


def test_pipeline_end_to_end_with_local_store(tmp_path):
    figure = run(DirStore(tmp_path / "landing"), DT, tmp_path)
    assert figure.read_text(encoding="utf-8").lstrip().startswith(("<?xml", "<svg"))
    outcome = results(tmp_path)
    assert len(outcome) == len(quality.CHECKS)
    assert {name for name, severity, passed in outcome if not passed} == {"events の event_id が重複していない"}
    assert all(severity == "warn" for _, severity, passed in outcome if not passed)  # 落ちたのは warn だけ
    # 置き場所の決まり: 3 つの表と、最後の印
    assert (tmp_path / "landing" / "raw" / f"dt={DT}" / "_SUCCESS").is_file()


def test_rerun_gives_same_result(tmp_path):
    store = DirStore(tmp_path / "landing")
    run(store, DT, tmp_path)
    first = (sales_total(tmp_path), results(tmp_path))
    run(store, DT, tmp_path)
    assert (sales_total(tmp_path), results(tmp_path)) == first  # 冪等: dq_results も 2 組にならない


def test_load_refuses_partition_without_success_marker(tmp_path):
    store = DirStore(tmp_path)
    ingest.land(store, DT)
    (tmp_path / "raw" / f"dt={DT}" / "_SUCCESS").unlink()
    con = duckdb.connect()
    with pytest.raises(RuntimeError, match="_SUCCESS"):
        ingest.load_raw(con, store, DT)


def test_error_check_stops_before_figure(tmp_path):
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


def test_pipeline_with_minio(tmp_path, s3_client):
    bucket = f"b16-{uuid.uuid4().hex[:8]}"
    store = S3Store(s3_client, bucket)
    try:
        run(store, DT, tmp_path)
        keys = {o["Key"] for o in s3_client.list_objects_v2(Bucket=bucket)["Contents"]}
        assert keys == {f"raw/dt={DT}/{n}" for n in ("orders.parquet", "order_items.parquet", "events.parquet", "_SUCCESS")}
        assert sales_total(tmp_path)[0] > 0
    finally:
        for key in list(s3_client.list_objects_v2(Bucket=bucket).get("Contents", [])):
            s3_client.delete_object(Bucket=bucket, Key=key["Key"])
        s3_client.delete_bucket(Bucket=bucket)


def test_interview_queries_run(tmp_path):
    run(DirStore(tmp_path / "landing"), DT, tmp_path)
    con = duckdb.connect(str(tmp_path / "warehouse.duckdb"), read_only=True)
    statements = [s.strip() for s in (Path(__file__).parent / "interview.sql").read_text(encoding="utf-8").split(";")]
    outputs = [con.execute(s).fetchall() for s in statements if "SELECT" in s]
    assert len(outputs) == 3
    first_orders, moving, check = outputs
    assert len({r[0] for r in first_orders}) == len(first_orders)  # 顧客ごとに 1 行
    assert len(moving) == sales_total(tmp_path)[0]
    assert check == [(3000, 3000)]  # 全注文に明細がある
