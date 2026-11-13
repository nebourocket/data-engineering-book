"""本番の DB を読むときの作法: 読み取り専用・時間制限・短いトランザクションで少しずつ。"""
import time

import psycopg

from b07_db import connect, reset_schema

# 接続のオプション。default_transaction_read_only は「既定」を決めるだけで、利用者が SET で切り替えられる。
# 本当に書かせないなら、読み取り専用のユーザー（権限）と併用する。
READ_OPTIONS = ("-c search_path=b07 -c default_transaction_read_only=on"
                " -c statement_timeout=30s -c idle_in_transaction_session_timeout=60s")


def read_in_batches(dsn: str, batch_size: int = 1000):
    """キーの続きから batch_size 件ずつ読む（keyset）。1 バッチを 1 つの短いトランザクションで読み、すぐ閉じる。"""
    last_id = 0
    with psycopg.connect(dsn, options=READ_OPTIONS, application_name="de-book-extract") as conn:
        while True:
            rows = conn.execute(
                "SELECT order_id, status FROM orders WHERE order_id > %s ORDER BY order_id LIMIT %s",
                (last_id, batch_size)).fetchall()
            conn.commit()  # 次のバッチを読む前にトランザクションを終える
            if not rows:
                return
            yield rows
            last_id = rows[-1][0]


def prepare(dsn: str, n: int) -> None:
    reset_schema(dsn)
    with connect(dsn) as conn:
        conn.execute("CREATE TABLE orders (order_id int PRIMARY KEY, status text NOT NULL)")
        conn.execute("INSERT INTO orders SELECT g, 'placed' FROM generate_series(1, %s) AS g", (n,))


def write_is_refused(dsn: str) -> str:
    """読み取り専用の接続から書こうとすると、PostgreSQL が断る。"""
    with psycopg.connect(dsn, options="-c search_path=b07 -c default_transaction_read_only=on") as conn:
        try:
            conn.execute("DELETE FROM orders")
        except psycopg.errors.ReadOnlySqlTransaction as e:
            return e.diag.message_primary
    return "書けてしまった"


def readonly_can_be_switched(dsn: str) -> int:
    """default_transaction_read_only は利用者が切り替えられる。切り替えると、書けてしまう。"""
    with psycopg.connect(dsn, options="-c search_path=b07 -c default_transaction_read_only=on",
                         autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = off")
        return conn.execute("DELETE FROM orders WHERE order_id = 1").rowcount


# 誰がどのくらい長くトランザクションを開きっぱなしにしているか（監視の SQL。読むだけなので本番でも安全）。
LONG_TRANSACTIONS_SQL = """
SELECT pid, application_name, state, now() - xact_start AS open_for
FROM pg_stat_activity
WHERE xact_start IS NOT NULL AND pid <> pg_backend_pid()
ORDER BY xact_start
"""


def named_cursor_keeps_transaction_open(dsn: str) -> str:
    """名前付きカーソルはメモリを節約できるが、読み終わるまでトランザクションを開き続ける。"""
    with psycopg.connect(dsn, options="-c search_path=b07", application_name="de-book-cursor") as conn:
        with conn.cursor(name="extract") as cur:
            cur.execute("SELECT order_id FROM orders ORDER BY order_id")
            cur.fetchmany(10)  # 少し読んだところで止める
            with psycopg.connect(dsn, autocommit=True) as watcher:
                rows = watcher.execute(LONG_TRANSACTIONS_SQL).fetchall()
    return next(r[2] for r in rows if r[1] == "de-book-cursor")


def show_my_session(dsn: str) -> list[tuple]:
    """トランザクションを開いたままの接続が、LONG_TRANSACTIONS_SQL に application_name つきで見える。"""
    holder = psycopg.connect(dsn, application_name="de-book-forgotten")
    holder.execute("SELECT 1")  # トランザクションが始まり、COMMIT しないので開きっぱなしになる
    with psycopg.connect(dsn, autocommit=True) as watcher:
        rows = watcher.execute(LONG_TRANSACTIONS_SQL).fetchall()
    holder.close()
    return [r for r in rows if r[1] == "de-book-forgotten"]


def idle_timeout_kills_forgotten_transaction(dsn: str) -> str:
    """idle_in_transaction_session_timeout を過ぎると、PostgreSQL が開きっぱなしの接続を切る。"""
    conn = psycopg.connect(dsn, options="-c idle_in_transaction_session_timeout=300ms")
    conn.execute("SELECT 1")  # トランザクションを開いたまま、何もしない
    time.sleep(0.8)
    try:
        conn.execute("SELECT 1")
    except psycopg.errors.IdleInTransactionSessionTimeout as e:
        return type(e).__name__
    finally:
        conn.close()
    return "切られなかった"


if __name__ == "__main__":
    import os

    dsn = os.environ["PG_DSN"]
    prepare(dsn, 2500)
    print([len(rows) for rows in read_in_batches(dsn)])
    print(write_is_refused(dsn))
    print(named_cursor_keeps_transaction_open(dsn))
    print(show_my_session(dsn))
    print(idle_timeout_kills_forgotten_transaction(dsn))
    print(readonly_can_be_switched(dsn))
