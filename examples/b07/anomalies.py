"""2 つの接続で、分離レベルごとの異常（ダーティリード・反復不能読み取りなど）を起こして見ます。

接続 a と b を同じプロセスの中で交互に動かします。psql を 2 つ開いて、同じ順に打つのと同じことです。
"""
import psycopg

from b07_db import connect, reset_schema

LEVELS = ["READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"]

SETUP_SQL = """
CREATE TABLE stock (product_id int PRIMARY KEY, quantity int NOT NULL);
INSERT INTO stock VALUES (1, 10);
CREATE TABLE pending_orders (order_id int PRIMARY KEY, status text NOT NULL);
INSERT INTO pending_orders VALUES (1, 'placed'), (2, 'placed');
CREATE TABLE shifts (staff text PRIMARY KEY, on_duty boolean NOT NULL);
INSERT INTO shifts VALUES ('hanako', true), ('ken', true)
"""


def fresh(dsn: str):
    """表を作り直し、接続 a と b を返します。"""
    reset_schema(dsn)
    a, b = connect(dsn), connect(dsn)
    for statement in SETUP_SQL.split(";\n"):
        a.execute(statement)
    return a, b


def read_stock(conn) -> int:
    return conn.execute("SELECT quantity FROM stock WHERE product_id = 1").fetchone()[0]


def dirty_read(dsn: str, level: str) -> int:
    """a がまだ COMMIT していない更新を、b が読めるか。読めたら 0、読めなければ 10 が返る。"""
    a, b = fresh(dsn)
    a.execute(f"BEGIN ISOLATION LEVEL {level}")
    a.execute("UPDATE stock SET quantity = 0 WHERE product_id = 1")
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    seen = read_stock(b)
    a.execute("ROLLBACK")
    b.execute("COMMIT")
    return seen


def non_repeatable_read(dsn: str, level: str) -> tuple[int, int]:
    """b が同じ行を 2 回読む間に、a が更新して COMMIT する。2 回の値が変わるか。"""
    a, b = fresh(dsn)
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    first = read_stock(b)
    a.execute("UPDATE stock SET quantity = 7 WHERE product_id = 1")
    second = read_stock(b)
    b.execute("COMMIT")
    return first, second


def phantom_read(dsn: str, level: str) -> tuple[int, int]:
    """b が同じ条件で 2 回数える間に、a が条件に合う行を足して COMMIT する。件数が変わるか。"""
    a, b = fresh(dsn)
    count = "SELECT count(*) FROM pending_orders WHERE status = 'placed'"
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    first = b.execute(count).fetchone()[0]
    a.execute("INSERT INTO pending_orders VALUES (3, 'placed')")
    second = b.execute(count).fetchone()[0]
    b.execute("COMMIT")
    return first, second


def lost_update(dsn: str, level: str) -> tuple[int, str | None]:
    """a も b も在庫を読み、読んだ値から計算した結果を書き戻す。a は 3 個、b は 2 個売る。

    正しい最終在庫は 10 - 3 - 2 = 5。戻り値は (最終在庫, b の更新が失敗したときのエラー名)。
    """
    a, b = fresh(dsn)
    a.execute(f"BEGIN ISOLATION LEVEL {level}")
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    seen_a, seen_b = read_stock(a), read_stock(b)
    a.execute("UPDATE stock SET quantity = %s WHERE product_id = 1", (seen_a - 3,))
    a.execute("COMMIT")
    error = None
    try:
        b.execute("UPDATE stock SET quantity = %s WHERE product_id = 1", (seen_b - 2,))
        b.execute("COMMIT")
    except psycopg.errors.SerializationFailure as e:
        error = type(e).__name__
        b.execute("ROLLBACK")
    return read_stock(a), error


def atomic_update(dsn: str, level: str) -> int:
    """直し方 1: 読んだ値を持ち回らず、データベースの中で引き算する。"""
    a, b = fresh(dsn)
    a.execute(f"BEGIN ISOLATION LEVEL {level}")
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    a.execute("UPDATE stock SET quantity = quantity - 3 WHERE product_id = 1")
    a.execute("COMMIT")
    b.execute("UPDATE stock SET quantity = quantity - 2 WHERE product_id = 1")
    b.execute("COMMIT")
    return read_stock(a)


def select_for_update(dsn: str) -> tuple[int, int]:
    """直し方 2: 読むときに行ロックを取る。b の SELECT ... FOR UPDATE は a の COMMIT まで待つ。"""
    a, b = fresh(dsn)
    a.execute("BEGIN")
    seen_a = a.execute("SELECT quantity FROM stock WHERE product_id = 1 FOR UPDATE").fetchone()[0]
    b.execute("SET lock_timeout = '300ms'")
    b.execute("BEGIN")
    try:
        b.execute("SELECT quantity FROM stock WHERE product_id = 1 FOR UPDATE")
        blocked = False
    except psycopg.errors.LockNotAvailable:
        blocked = True
        b.execute("ROLLBACK")
    a.execute("UPDATE stock SET quantity = %s WHERE product_id = 1", (seen_a - 3,))
    a.execute("COMMIT")
    b.execute("BEGIN")
    seen_b = b.execute("SELECT quantity FROM stock WHERE product_id = 1 FOR UPDATE").fetchone()[0]
    b.execute("COMMIT")
    return int(blocked), seen_b


def write_skew(dsn: str, level: str) -> tuple[int, str | None]:
    """「店番は必ず 1 人は残す」規則で、a と b が同時に自分だけ休みを取る。

    どちらも「2 人いるから自分は休める」と確かめてから、自分の行だけ更新する。
    戻り値は (最後に出勤している人数, 後から来た側のエラー名)。
    """
    a, b = fresh(dsn)
    on_duty = "SELECT count(*) FROM shifts WHERE on_duty"
    a.execute(f"BEGIN ISOLATION LEVEL {level}")
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    assert a.execute(on_duty).fetchone()[0] == 2 and b.execute(on_duty).fetchone()[0] == 2
    a.execute("UPDATE shifts SET on_duty = false WHERE staff = 'hanako'")
    b.execute("UPDATE shifts SET on_duty = false WHERE staff = 'ken'")
    a.execute("COMMIT")
    error = None
    try:
        b.execute("COMMIT")
    except psycopg.errors.SerializationFailure as e:
        error = type(e).__name__
    return a.execute(on_duty).fetchone()[0], error


if __name__ == "__main__":
    import os

    dsn = os.environ["PG_DSN"]
    for level in LEVELS:
        print(f"{level:17} ダーティリード={dirty_read(dsn, level)} 反復不能={non_repeatable_read(dsn, level)}"
              f" ファントム={phantom_read(dsn, level)} 更新の消失={lost_update(dsn, level)}"
              f" 書き込みスキュー={write_skew(dsn, level)}")
    print("原子的な更新", atomic_update(dsn, "READ COMMITTED"), "FOR UPDATE", select_for_update(dsn))
