"""ケーススタディ: 注文テーブルを DWH に写す 3 つの方法 (全件・updated_at の差分・WAL) を同じ 1 日の変更で比べます。"""
import random
import time

import psycopg

import logical
import query_cdc
from sandbox import sandbox


def run(dsn, n=20000, updates=600, deletes=40, slow=10, seed=4):
    """n 件の注文に 1 日分の変更 (更新 updates・削除 deletes・コミットが遅れる更新 slow) を行います。

    3 つの方法それぞれについて、「読み始めてから写しに反映し終えるまで」の秒数と、写しのずれた行数を返します。
    全件の取り直しは、遅れたトランザクションがまだコミットされていない時 (1 回目) と、コミットされた後 (次の回) の 2 回行います。
    """
    rng = random.Random(seed)
    ids = rng.sample(range(1, n + 1), updates + deletes + slow)
    upd, dele, late = ids[:updates], ids[updates:updates + deletes], ids[updates + deletes:]
    seconds = {}
    with sandbox(dsn, "shop") as box, psycopg.connect(dsn, autocommit=True) as admin:
        with box.connect() as setup:
            setup.execute(query_cdc.SETUP)
            setup.execute("INSERT INTO orders (order_id, customer_id, status, amount) "
                          "SELECT i, 1 + i %% 500, 'placed', 1000 + i %% 7 * 100 FROM generate_series(1, %s) AS i", (n,))
            setup.execute("CREATE PUBLICATION case_pub FOR TABLE orders")
        logical.create_slot(admin, "case_slot", "pgoutput")
        try:
            with box.connect(autocommit=True) as poller, box.connect() as slow_tx, box.connect(autocommit=True) as fast:
                rows, mark = query_cdc.poll(poller, "-infinity")
                copy_query = {r[0]: r[1] for r in rows}
                copy_log = dict(copy_query)
                wal_start = admin.execute("SELECT pg_current_wal_lsn()").fetchone()[0]
                for i in late:  # コミットが遅れる更新を先に始める
                    slow_tx.execute("UPDATE orders SET status = 'cancelled', updated_at = now() WHERE order_id = %s", (i,))
                time.sleep(0.05)
                for i in upd:
                    fast.execute("UPDATE orders SET status = 'shipped', updated_at = now() WHERE order_id = %s", (i,))
                for i in dele:
                    fast.execute("DELETE FROM orders WHERE order_id = %s", (i,))

                start = time.perf_counter()  # 全件の取り直し 1 回目 (遅れた更新はまだ確定していない)
                copy_full_first = dict(fast.execute("SELECT order_id, status FROM orders").fetchall())
                seconds["full_reload"] = time.perf_counter() - start

                start = time.perf_counter()  # updated_at の差分 (1 回目と、遅れたコミットの後の 2 回目)
                seen, mark = query_cdc.poll(poller, mark)
                slow_tx.commit()
                seen_late, mark = query_cdc.poll(poller, mark)
                for r in seen + seen_late:
                    copy_query[r[0]] = r[1]
                seconds["updated_at"] = time.perf_counter() - start

                truth = dict(fast.execute("SELECT order_id, status FROM orders").fetchall())
                copy_full_next = dict(fast.execute("SELECT order_id, status FROM orders").fetchall())
                wal_bytes = admin.execute("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), %s)::bigint", (wal_start,)).fetchone()[0]

                start = time.perf_counter()  # WAL: 読む + 解釈する + 写しに反映する
                changes = logical.PgoutputDecoder().changes(logical.read_pgoutput(admin, "case_slot", "case_pub"))
                for c in changes:
                    key = (c["new"] or c["old"])["order_id"]
                    if c["op"] == "delete":
                        copy_log.pop(key, None)
                    else:
                        copy_log[key] = c["new"]["status"]
                seconds["wal"] = time.perf_counter() - start
        finally:
            logical.drop_slot(admin, "case_slot")
            with box.connect(autocommit=True) as c:
                c.execute("DROP PUBLICATION case_pub")

    def wrong(copy):
        return sum(1 for k in set(copy) | set(truth) if copy.get(k) != truth.get(k))

    return {
        "orders": n, "changes_in_source": updates + deletes + slow,
        "rows_read": {"full_reload": n, "updated_at": len(seen) + len(seen_late), "wal": len(changes)},
        "wrong_rows_after": {"full_reload_first": wrong(copy_full_first), "full_reload_next_run": wrong(copy_full_next),
                             "updated_at": wrong(copy_query), "wal": wrong(copy_log)},
        "seconds_to_finish": {k: round(v, 3) for k, v in seconds.items()},
        "wal_bytes_per_change": round(wal_bytes / (updates + deletes + slow)),
    }


def wal_per_update(dsn, identity, updates=1000):
    """1 行の更新 (自動コミット) 1 回あたりの WAL のバイト数と、放置したスロットが止める WAL の増え方を測ります。

    identity は表の REPLICA IDENTITY (DEFAULT か FULL)。
    """
    with sandbox(dsn, "shop") as box, psycopg.connect(dsn, autocommit=True) as admin:
        with box.connect(autocommit=True) as conn:
            conn.execute(query_cdc.SETUP)
            conn.execute("INSERT INTO orders (order_id, customer_id, status, amount) "
                         "SELECT i, 1 + i % 500, 'placed', 1000 + i % 7 * 100 FROM generate_series(1, 5000) AS i")
            conn.execute(f"ALTER TABLE orders REPLICA IDENTITY {identity}")
            conn.execute("CREATE PUBLICATION wal_pub FOR TABLE orders")
            logical.create_slot(admin, "wal_slot", "pgoutput")
            try:
                start = admin.execute("SELECT pg_current_wal_lsn()").fetchone()[0]
                before = logical.slot_status(admin, "wal_slot")["retained_bytes"]
                for i in range(1, updates + 1):
                    conn.execute("UPDATE orders SET status = 'shipped', updated_at = now() WHERE order_id = %s", (i,))
                total = admin.execute("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), %s)::bigint", (start,)).fetchone()[0]
                held = logical.slot_status(admin, "wal_slot")["retained_bytes"] - before
            finally:
                logical.drop_slot(admin, "wal_slot")
                conn.execute("DROP PUBLICATION wal_pub")
    return {"identity": identity, "wal_bytes_per_update": round(total / updates),
            "idle_slot_holds_per_update": round(held / updates)}
