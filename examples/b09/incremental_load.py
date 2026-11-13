"""PostgreSQL (スキーマ b09) の orders を、ウォーターマークで差分だけ DuckDB に取り込みます。

ウォーターマーク = 「ここまで取り込んだ」印。取り込み先と同じ DuckDB に置くので、
データの書き込みと印の更新を 1 つのトランザクションにできます。
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import generate  # noqa: E402

JST = timezone(timedelta(hours=9))


def setup_source(pg_dsn):
    """取り込み元を作り直します。orders の ordered_at を JST とみなして updated_at に入れます。"""
    data = generate()
    amounts = {}
    for item in data["order_items"]:
        amounts[item["order_id"]] = amounts.get(item["order_id"], 0) + item["quantity"] * item["unit_price"]
    rows = [(o["order_id"], o["customer_id"], o["status"].lower(), amounts[o["order_id"]],
             datetime.strptime(o["ordered_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST))
            for o in data["orders"]]
    with psycopg.connect(pg_dsn) as con:
        con.execute("DROP SCHEMA IF EXISTS b09 CASCADE")
        con.execute("CREATE SCHEMA b09")
        con.execute("""
            CREATE TABLE b09.orders (
                order_id    integer PRIMARY KEY,
                customer_id integer NOT NULL,
                status      text NOT NULL,
                amount      integer NOT NULL,
                updated_at  timestamptz NOT NULL
            )""")
        with con.cursor() as cur:
            cur.executemany("INSERT INTO b09.orders VALUES (%s, %s, %s, %s, %s)", rows)


def setup_target(duck):
    duck.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id    INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            status      VARCHAR NOT NULL,
            amount      INTEGER NOT NULL,
            updated_at  TIMESTAMPTZ NOT NULL
        )""")
    duck.execute("CREATE TABLE IF NOT EXISTS watermark (name VARCHAR PRIMARY KEY, value TIMESTAMPTZ)")


def read_watermark(duck):
    row = duck.execute("SELECT value FROM watermark WHERE name = 'orders'").fetchone()
    return row[0] if row else datetime(1970, 1, 1, tzinfo=timezone.utc)


def extract(pg_dsn, watermark, lookback):
    """ウォーターマークより (lookback 分だけ手前から) 新しい行を取り出します。"""
    with psycopg.connect(pg_dsn) as con:
        return con.execute(
            "SELECT order_id, customer_id, status, amount, updated_at FROM b09.orders "
            "WHERE updated_at > %s ORDER BY updated_at, order_id",
            (watermark - lookback,)).fetchall()


UPSERT = """
    INSERT INTO orders
    SELECT * FROM batch
    ON CONFLICT (order_id) DO UPDATE SET
        customer_id = excluded.customer_id,
        status = excluded.status,
        amount = excluded.amount,
        updated_at = excluded.updated_at
"""


def load(duck, pg_dsn, lookback=timedelta(0)):
    """差分を取り出して upsert し、ウォーターマークを進めます。取り込んだ件数を返します。"""
    rows = extract(pg_dsn, read_watermark(duck), lookback)
    if not rows:
        return 0
    batch = pa.table({
        "order_id": [r[0] for r in rows], "customer_id": [r[1] for r in rows],
        "status": [r[2] for r in rows], "amount": [r[3] for r in rows],
        "updated_at": pa.array([r[4] for r in rows], pa.timestamp("us", tz="UTC"))})
    duck.execute("BEGIN")
    try:
        duck.register("batch", batch)
        duck.execute(UPSERT)
        duck.unregister("batch")
        # 取り込んだ行の updated_at の最大値を新しい印にする (印は後戻りさせない)
        duck.execute("""
            INSERT INTO watermark VALUES ('orders', ?)
            ON CONFLICT (name) DO UPDATE SET value = greatest(watermark.value, excluded.value)""",
                     [max(r[4] for r in rows)])
        duck.execute("COMMIT")
    except Exception:
        duck.execute("ROLLBACK")
        raise
    return len(rows)


def sync_deletes(duck, pg_dsn):
    """元で消えた行を、キーの突き合わせで見つけて取り込み先からも消します。消した件数を返します。"""
    with psycopg.connect(pg_dsn) as con:
        source_ids = {r[0] for r in con.execute("SELECT order_id FROM b09.orders")}
    target_ids = {r[0] for r in duck.execute("SELECT order_id FROM orders").fetchall()}
    gone = sorted(target_ids - source_ids)
    for order_id in gone:
        duck.execute("DELETE FROM orders WHERE order_id = ?", [order_id])
    return len(gone)
