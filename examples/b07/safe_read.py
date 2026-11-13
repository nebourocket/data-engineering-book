"""本番の DB を読むときの作法: 読み取り専用・時間制限・名前付きカーソルで少しずつ。"""
import psycopg

from b07_db import connect, reset_schema


def read_in_batches(dsn: str, batch_size: int = 1000):
    """表を batch_size 件ずつ読む。接続の設定で、書き込みと長居を止めておく。"""
    with psycopg.connect(
        dsn,
        options="-c search_path=b07 -c default_transaction_read_only=on"
                " -c statement_timeout=30s -c idle_in_transaction_session_timeout=60s",
        application_name="de-book-extract",
    ) as conn:
        with conn.cursor(name="extract") as cur:  # 名前付きカーソル: サーバー側に結果を置き、少しずつ取る
            cur.execute("SELECT order_id, status FROM orders ORDER BY order_id")
            while rows := cur.fetchmany(batch_size):
                yield rows


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


# 誰がどのくらい長く取引を開きっぱなしにしているか（監視の SQL。読むだけなので本番でも安全）。
LONG_TRANSACTIONS_SQL = """
SELECT pid, application_name, state, now() - xact_start AS open_for
FROM pg_stat_activity
WHERE xact_start IS NOT NULL AND pid <> pg_backend_pid()
ORDER BY xact_start
"""


def show_my_session(dsn: str) -> list[tuple]:
    """取引を開いたままの接続が、LONG_TRANSACTIONS_SQL に application_name つきで見える。"""
    holder = psycopg.connect(dsn, application_name="de-book-forgotten")
    holder.execute("SELECT 1")  # 取引が始まり、COMMIT しないので開きっぱなしになる
    with psycopg.connect(dsn, autocommit=True) as watcher:
        rows = watcher.execute(LONG_TRANSACTIONS_SQL).fetchall()
    holder.close()
    return [r for r in rows if r[1] == "de-book-forgotten"]


if __name__ == "__main__":
    import os

    dsn = os.environ["PG_DSN"]
    prepare(dsn, 2500)
    print([len(rows) for rows in read_in_batches(dsn)])
    print(write_is_refused(dsn))
    print(show_my_session(dsn))
