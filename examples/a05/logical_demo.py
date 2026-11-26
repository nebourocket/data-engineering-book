"""論理デコーディングの実演 (wal_level=logical の PostgreSQL が要ります)。"""
import time

import psycopg

import logical
import query_cdc
from envelope import event_key, to_envelope
from sandbox import sandbox


def wal_sees_everything(dsn):
    """query_cdc と同じ 5 回の変更を、スロット経由で読んで数えます (test_decoding)。"""
    with sandbox(dsn, "shop") as box, psycopg.connect(dsn, autocommit=True) as admin:
        logical.create_slot(admin, "a5_compare", "test_decoding")
        try:
            query_cdc.run_scenario(box)
            lines = logical.read_test_decoding(admin, "a5_compare")
        finally:
            logical.drop_slot(admin, "a5_compare")
    changes = [ln for ln in lines if ": UPDATE:" in ln or ": DELETE:" in ln]
    return lines, changes


def pgoutput_events(dsn, replica_identity_full):
    """注文を 1 件入れ、更新し、削除して、pgoutput から読んだ変更をエンベロープにして返します。"""
    with sandbox(dsn, "shop") as box, psycopg.connect(dsn, autocommit=True) as admin:
        with box.connect(autocommit=True) as conn:
            conn.execute("CREATE TABLE orders (order_id integer PRIMARY KEY, status text, amount integer)")
            if replica_identity_full:
                conn.execute("ALTER TABLE orders REPLICA IDENTITY FULL")
            conn.execute("CREATE PUBLICATION a5_pub FOR TABLE orders")
            logical.create_slot(admin, "a5_pgoutput", "pgoutput")
            try:
                conn.execute("INSERT INTO orders VALUES (1, 'placed', 1200)")
                conn.execute("UPDATE orders SET status = 'paid' WHERE order_id = 1")
                conn.execute("UPDATE orders SET order_id = 10 WHERE order_id = 1")
                conn.execute("DELETE FROM orders WHERE order_id = 10")
                messages = logical.read_pgoutput(admin, "a5_pgoutput", "a5_pub")
            finally:
                logical.drop_slot(admin, "a5_pgoutput")
                conn.execute("DROP PUBLICATION a5_pub")
    changes = logical.PgoutputDecoder().changes(messages)
    kinds = [m[2][:1].decode() for m in messages]
    envelopes = [to_envelope(c, db="postgres") for c in changes]
    return kinds, changes, envelopes, [event_key(c) for c in changes]


def slot_keeps_wal(dsn, writes=20000):
    """読み手のいないスロットがあると、WAL が捨てられずに増えることを測ります。"""
    with sandbox(dsn, "shop") as box, psycopg.connect(dsn, autocommit=True) as admin:
        with box.connect(autocommit=True) as conn:
            conn.execute("CREATE TABLE t (id serial PRIMARY KEY, pad text)")
            logical.create_slot(admin, "a5_idle", "pgoutput")
            try:
                before = logical.slot_status(admin, "a5_idle")
                conn.execute("INSERT INTO t (pad) SELECT repeat('x', 200) FROM generate_series(1, %s)", (writes,))
                admin.execute("CHECKPOINT")
                after = logical.slot_status(admin, "a5_idle")
            finally:
                logical.drop_slot(admin, "a5_idle")
    return before, after


def slot_gets_lost(dsn, keep="32MB", writes=400000):
    """max_slot_wal_keep_size を小さくして放置すると、スロットが lost になって読み直せなくなります。"""
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f"ALTER SYSTEM SET max_slot_wal_keep_size = '{keep}'")
        admin.execute("SELECT pg_reload_conf()")
        time.sleep(1)  # 設定の再読み込みを待つ
        admin.execute("CREATE PUBLICATION a5_all FOR ALL TABLES")
        logical.create_slot(admin, "a5_lost", "pgoutput")
        try:
            admin.execute("CREATE TABLE IF NOT EXISTS a5_wal_fill (id serial, pad text)")
            for _ in range(3):
                admin.execute("INSERT INTO a5_wal_fill (pad) SELECT repeat('x', 200) FROM generate_series(1, %s)",
                              (writes,))
                admin.execute("SELECT pg_switch_wal()")
                admin.execute("CHECKPOINT")
            status = logical.slot_status(admin, "a5_lost")
            try:
                logical.read_pgoutput(admin, "a5_lost", "a5_all")
                error = None
            except psycopg.Error as exc:
                error = str(exc).splitlines()[0]
        finally:
            logical.drop_slot(admin, "a5_lost")
            admin.execute("DROP PUBLICATION a5_all")
            admin.execute("DROP TABLE a5_wal_fill")
            admin.execute("ALTER SYSTEM RESET max_slot_wal_keep_size")
            admin.execute("SELECT pg_reload_conf()")
    return status, error
