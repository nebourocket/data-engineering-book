import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import api_client
import duckdb
import fake_api
import incremental_load as inc
import landing_files as landing
import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import generate  # noqa: E402


def test_fetch_all_pages_waits_on_429_and_checks_token():
    orders = generate()["orders"]
    waits = []
    with fake_api.FakeApi(orders, reject_first=2) as api:
        rows = api_client.fetch_all(api.url, fake_api.TOKEN, limit=500, sleep=waits.append)
        assert len(rows) == 3000 and len({r["order_id"] for r in rows}) == 3000
        assert waits == [1.0, 1.0]  # 429 が 2 回 → Retry-After の 1 秒を 2 回
        assert api.requests == 2 + 6  # 429 が 2 回 + 3,000 件 / 500 件 = 6 ページ
        with pytest.raises(Exception, match="401"):
            api_client.get_json(f"{api.url}/orders", "wrong-token")


def test_bigger_pages_need_fewer_requests():
    with fake_api.FakeApi(generate()["orders"], reject_first=2) as api:
        api_client.fetch_all(api.url, fake_api.TOKEN, limit=1000, sleep=lambda s: None)
        assert api.requests == 2 + 3  # 3,000 件 / 1,000 件 = 3 ページ


def test_gives_up_when_429_continues():
    with fake_api.FakeApi([], reject_first=99) as api:
        with pytest.raises(RuntimeError, match="429"):
            api_client.get_json(f"{api.url}/orders", fake_api.TOKEN, sleep=lambda s: None, max_attempts=3)
        assert api.requests == 3


@pytest.fixture
def source(pg_dsn):
    inc.setup_source(pg_dsn)
    duck = duckdb.connect()
    inc.setup_target(duck)
    yield pg_dsn, duck
    duck.close()


def test_incremental_load_and_idempotency(source):
    pg_dsn, duck = source
    assert inc.load(duck, pg_dsn) == 3000
    assert inc.load(duck, pg_dsn) == 0  # 変化が無ければ何もしない
    # 元で 2 件を更新し、1 件を追加する
    with psycopg.connect(pg_dsn) as con:
        con.execute("UPDATE b09.orders SET status = 'cancelled', updated_at = now() WHERE order_id IN (1, 2)")
        con.execute("INSERT INTO b09.orders VALUES (9001, 1, 'placed', 1000, now())")
    assert inc.load(duck, pg_dsn) == 3
    assert duck.execute("SELECT count(*) FROM orders").fetchone() == (3001,)
    assert duck.execute("SELECT status FROM orders WHERE order_id = 1").fetchone() == ("cancelled",)
    # 同じ範囲をもう一度読み直しても (lookback)、件数も中身も変わらない
    before = duck.execute("SELECT * FROM orders ORDER BY order_id").fetchall()
    assert inc.load(duck, pg_dsn, lookback=timedelta(days=400)) == 3001
    assert duck.execute("SELECT * FROM orders ORDER BY order_id").fetchall() == before


def test_late_committed_row_needs_lookback(source):
    pg_dsn, duck = source
    inc.load(duck, pg_dsn)
    watermark = inc.read_watermark(duck)
    # 印より古い updated_at の行が、あとからコミットされた状況
    with psycopg.connect(pg_dsn) as con:
        con.execute("INSERT INTO b09.orders VALUES (9002, 1, 'placed', 500, %s)", (watermark - timedelta(minutes=5),))
    assert inc.load(duck, pg_dsn) == 0  # 見落とす
    assert inc.load(duck, pg_dsn, lookback=timedelta(hours=1)) >= 1  # 1 時間戻して読めば拾える
    assert duck.execute("SELECT count(*) FROM orders WHERE order_id = 9002").fetchone() == (1,)
    assert inc.read_watermark(duck) == watermark  # 印は後戻りしない


def test_deletes_are_found_by_comparing_keys(source):
    pg_dsn, duck = source
    inc.load(duck, pg_dsn)
    with psycopg.connect(pg_dsn) as con:
        con.execute("DELETE FROM b09.orders WHERE order_id = 10")
    assert inc.load(duck, pg_dsn) == 0  # updated_at では削除が見えない
    assert inc.sync_deletes(duck, pg_dsn) == 1
    assert duck.execute("SELECT count(*) FROM orders").fetchone() == (2999,)


def test_merge_sql_gives_same_result_as_on_conflict(source):
    pg_dsn, duck = source
    inc.load(duck, pg_dsn)
    rows = inc.extract(pg_dsn, datetime(1970, 1, 1, tzinfo=timezone.utc), timedelta(0))[:5]
    import pyarrow as pa

    batch = pa.table({"order_id": [r[0] for r in rows], "customer_id": [r[1] for r in rows],
                      "status": ["cancelled"] * 5, "amount": [r[3] for r in rows],
                      "updated_at": pa.array([r[4] for r in rows], pa.timestamp("us", tz="UTC"))})
    duck.register("batch", batch)
    duck.execute((Path(inc.__file__).parent / "merge.sql").read_text(encoding="utf-8"))
    duck.unregister("batch")
    assert duck.execute("SELECT count(*) FROM orders").fetchone() == (3000,)  # 既存のキーなので増えない
    ids = [r[0] for r in rows]
    assert duck.execute("SELECT count(*) FROM orders WHERE status = 'cancelled' AND order_id = ANY(?)",
                        [ids]).fetchone()[0] == 5


@pytest.fixture
def bucket(s3_client):
    name = f"b09-{uuid.uuid4().hex[:8]}"
    s3_client.create_bucket(Bucket=name)
    yield name
    for page in s3_client.get_paginator("list_objects_v2").paginate(Bucket=name):
        for obj in page.get("Contents", []):
            s3_client.delete_object(Bucket=name, Key=obj["Key"])
    s3_client.delete_bucket(Bucket=name)


def test_landing_files_and_partition_replace(s3_client, bucket):
    events = generate()["events"]
    days = landing.land_events(s3_client, bucket, events)
    assert landing.list_ready_partitions(s3_client, bucket, "events") == days
    assert landing.list_ready_partitions(s3_client, bucket, "events", after_dt=days[-3]) == days[-2:]

    duck = duckdb.connect()
    landing.setup_raw(duck)
    for dt in days:
        landing.load_partition(duck, s3_client, bucket, dt)
    total = duck.execute("SELECT count(*), count(DISTINCT event_id) FROM events_raw").fetchone()
    assert total == (4040, 4000)  # raw 層には二重に届いた 40 件がそのまま残る
    late = duck.execute("SELECT count(*) FROM events_raw WHERE substr(event_time, 1, 10) <> dt").fetchone()[0]
    assert late > 0  # 遅れて届いた分は、届いた日のパーティションに入っている

    queries = [q.strip() for q in (Path(landing.__file__).parent / "exercises.sql").read_text(
        encoding="utf-8").split(";") if "SELECT" in q]
    assert duck.execute(queries[0][queries[0].index("SELECT"):]).fetchone() == (late,)
    assert duck.execute(queries[1][queries[1].index("SELECT"):]).fetchone() == (4,)

    # 同じパーティションを何度入れ直しても、件数は変わらない
    for _ in range(3):
        landing.load_partition(duck, s3_client, bucket, days[10])
    assert duck.execute("SELECT count(*) FROM events_raw").fetchone() == (4040,)


def test_new_column_does_not_break_ingestion(s3_client, bucket):
    event = {"event_id": 1, "customer_id": 1, "event_type": "view", "event_time": "2026-03-01 10:00:00",
             "received_at": "2026-03-01 10:00:05", "coupon_code": "SPRING"}  # 想定外の列
    landing.land_events(s3_client, bucket, [event])
    duck = duckdb.connect()
    landing.setup_raw(duck)
    assert landing.load_partition(duck, s3_client, bucket, "2026-03-01") == 1
    assert duck.execute("SELECT extra, source_file FROM events_raw").fetchone() == (
        '{"coupon_code": "SPRING"}', "landing/events/dt=2026-03-01/part-0000.jsonl.gz")
