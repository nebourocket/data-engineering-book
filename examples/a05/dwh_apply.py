"""CDC の変更ログを DWH (DuckDB) に反映します: MERGE、削除の扱い、SCD2 への変換。

MERGE INTO は DuckDB 1.4 以降、PostgreSQL 15 以降で使えます。QUALIFY は DuckDB の書き方です。
"""
import random
from datetime import datetime, timedelta

from neboske_shop import generate

LOG_DDL = """
CREATE TABLE cdc_log (
    lsn bigint, ts timestamp, op varchar, order_id integer,
    status varchar, amount integer, before_status varchar
)
"""
HARD_DDL = "CREATE TABLE orders_hard (order_id integer PRIMARY KEY, status varchar, amount integer)"
SOFT_DDL = """
CREATE TABLE orders_soft (
    order_id integer PRIMARY KEY, status varchar, amount integer, last_lsn bigint, is_deleted boolean
)
"""
LATEST = """
SELECT * FROM cdc_log WHERE lsn BETWEEN ? AND ?
QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY lsn DESC) = 1
"""
MERGE_HARD = f"""
MERGE INTO orders_hard AS t USING ({LATEST}) AS s ON t.order_id = s.order_id
WHEN MATCHED AND s.op = 'd' THEN DELETE
WHEN MATCHED THEN UPDATE SET status = s.status, amount = s.amount
WHEN NOT MATCHED AND s.op <> 'd' THEN INSERT VALUES (s.order_id, s.status, s.amount)
"""
MERGE_SOFT = f"""
MERGE INTO orders_soft AS t USING ({LATEST}) AS s ON t.order_id = s.order_id
WHEN MATCHED AND s.lsn > t.last_lsn THEN UPDATE SET
    status = CASE WHEN s.op = 'd' THEN t.status ELSE s.status END,
    amount = CASE WHEN s.op = 'd' THEN t.amount ELSE s.amount END,
    last_lsn = s.lsn, is_deleted = (s.op = 'd')
WHEN NOT MATCHED THEN INSERT VALUES (s.order_id, coalesce(s.status, s.before_status), s.amount, s.lsn, s.op = 'd')
"""
SCD2 = """
CREATE OR REPLACE TABLE orders_scd2 AS
SELECT order_id, status, amount, valid_from, valid_to, valid_to IS NULL AS is_current
FROM (
    SELECT order_id, op, status, amount, ts AS valid_from,
           lead(ts) OVER (PARTITION BY order_id ORDER BY lsn) AS valid_to
    FROM cdc_log
) WHERE op <> 'd'
"""
FLOW = ["placed", "paid", "shipped", "delivered"]


def make_changelog(n=1000, seed=1):
    """ねぼすけ商店の先頭 n 件の注文から、作成・更新・削除の変更ログを作ります (lsn は 1 から連番)。"""
    rng = random.Random(seed)
    orders = generate()["orders"][:n]
    base = datetime(2026, 1, 1)
    rows = []

    def add(op, order_id, status, amount, before=None):
        lsn = len(rows) + 1
        rows.append({"lsn": lsn, "ts": base + timedelta(minutes=lsn), "op": op, "order_id": order_id,
                     "status": status, "amount": amount, "before_status": before})

    for o in orders:
        add("c", o["order_id"], "placed", 1000 + o["order_id"] % 7 * 100)
    for o in orders:
        status, amount = "placed", 1000 + o["order_id"] % 7 * 100
        for nxt in FLOW[1:rng.randint(1, 4)]:
            add("u", o["order_id"], nxt, amount, status)
            status = nxt
        if rng.random() < 0.05:
            add("d", o["order_id"], None, None, status)
    return rows


def load_log(con, rows):
    con.execute(LOG_DDL)
    con.executemany("INSERT INTO cdc_log VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [tuple(r.values()) for r in rows])


def batches(max_lsn, size):
    """lsn の範囲 (下限, 上限) を size 件ずつに区切ります。"""
    return [(lo, min(lo + size - 1, max_lsn)) for lo in range(1, max_lsn + 1, size)]


def run_dwh(batch_size=300, shuffle_seed=None, replay_first=False):
    """バッチごとに MERGE して、ハード削除版とソフト削除版の行数を返します。

    shuffle_seed を渡すとバッチを入れ替えて適用し、replay_first が真なら最初のバッチをもう一度適用します。
    """
    import duckdb

    con = duckdb.connect()
    rows = make_changelog()
    load_log(con, rows)
    con.execute(HARD_DDL)
    con.execute(SOFT_DDL)
    plan = batches(len(rows), batch_size)
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(plan)
    if replay_first:
        plan = plan + [(1, batch_size)]
    for lo, hi in plan:
        con.execute(MERGE_HARD, [lo, hi])
        con.execute(MERGE_SOFT, [lo, hi])
    con.execute(SCD2)
    deleted = con.execute("SELECT count(DISTINCT order_id) FROM cdc_log WHERE op = 'd'").fetchone()[0]
    return {
        "log_rows": len(rows), "deleted_in_source": deleted,
        "hard_rows": con.execute("SELECT count(*) FROM orders_hard").fetchone()[0],
        "soft_rows": con.execute("SELECT count(*) FROM orders_soft").fetchone()[0],
        "soft_live": con.execute("SELECT count(*) FROM orders_soft WHERE NOT is_deleted").fetchone()[0],
        "scd2_rows": con.execute("SELECT count(*) FROM orders_scd2").fetchone()[0],
        "scd2_current": con.execute("SELECT count(*) FROM orders_scd2 WHERE is_current").fetchone()[0],
        "hard_state": con.execute("SELECT md5(string_agg(order_id || status, ',' ORDER BY order_id)) "
                                  "FROM orders_hard").fetchone()[0],
    }
