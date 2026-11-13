"""行ロックの待ち、デッドロック、MVCC の行バージョンを実際に見ます。"""
import threading
import time

import psycopg

from b07_db import connect, reset_schema

SETUP_SQL = """
CREATE TABLE stock (product_id int PRIMARY KEY, quantity int NOT NULL);
INSERT INTO stock VALUES (1, 10), (2, 20)
"""


def fresh(dsn: str):
    reset_schema(dsn)
    a, b = connect(dsn), connect(dsn)
    for statement in SETUP_SQL.split(";\n"):
        a.execute(statement)
    return a, b


def row_versions(dsn: str) -> tuple[tuple, tuple]:
    """UPDATE の前後で、行の物理的な位置 ctid と作った取引の番号 xmin がどう変わるか。"""
    a, _ = fresh(dsn)
    query = "SELECT ctid::text, xmin::text, xmax::text, quantity FROM stock WHERE product_id = 1"
    before = a.execute(query).fetchone()
    a.execute("UPDATE stock SET quantity = 9 WHERE product_id = 1")
    after = a.execute(query).fetchone()
    return before, after


def reader_is_not_blocked(dsn: str) -> tuple[int, str]:
    """a が行を更新中（未 COMMIT）でも、b の SELECT は待たずに更新前の値を読む。"""
    a, b = fresh(dsn)
    a.execute("BEGIN")
    a.execute("UPDATE stock SET quantity = 0 WHERE product_id = 1")
    b.execute("SET lock_timeout = '300ms'")
    seen = b.execute("SELECT quantity FROM stock WHERE product_id = 1").fetchone()[0]
    try:
        b.execute("UPDATE stock SET quantity = 5 WHERE product_id = 1")
        writer = "待たずに更新できた"
    except psycopg.errors.LockNotAvailable:
        writer = "更新は a の COMMIT を待って時間切れ"
    a.execute("ROLLBACK")
    return seen, writer


def deadlock(dsn: str, same_order: bool) -> list[str]:
    """a は商品 1 → 2、b は商品 2 → 1 の順に更新する。same_order=True なら b も 1 → 2 の順にする。

    戻り値は、エラーになった側の名前の一覧。デッドロックなら、PostgreSQL がどちらか 1 つを中止する。
    """
    a, b = fresh(dsn)
    failed = []

    def run(name, conn, first, second, pause):
        try:
            conn.execute("BEGIN")
            conn.execute("UPDATE stock SET quantity = quantity - 1 WHERE product_id = %s", (first,))
            time.sleep(pause)
            conn.execute("UPDATE stock SET quantity = quantity - 1 WHERE product_id = %s", (second,))
            conn.execute("COMMIT")
        except psycopg.errors.DeadlockDetected:
            failed.append(name)
            conn.execute("ROLLBACK")

    order_b = (1, 2) if same_order else (2, 1)
    threads = [threading.Thread(target=run, args=("a", a, 1, 2, 0.5)),
               threading.Thread(target=run, args=("b", b, *order_b, 0.5))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return failed


if __name__ == "__main__":
    import os

    dsn = os.environ["PG_DSN"]
    print(row_versions(dsn))
    print(reader_is_not_blocked(dsn))
    print("順番がばらばら", deadlock(dsn, same_order=False))
    print("順番をそろえた", deadlock(dsn, same_order=True))
