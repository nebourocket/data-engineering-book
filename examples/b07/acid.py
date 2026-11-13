"""トランザクションの原子性と、直列化失敗のやり直し（リトライ）。"""
import psycopg

from b07_db import connect, reset_schema

SETUP_SQL = """
CREATE TABLE stock (product_id int PRIMARY KEY, quantity int NOT NULL CHECK (quantity >= 0));
INSERT INTO stock VALUES (1, 5);
CREATE TABLE orders (order_id serial PRIMARY KEY, product_id int NOT NULL, quantity int NOT NULL);
CREATE TABLE shifts (staff text PRIMARY KEY, on_duty boolean NOT NULL);
INSERT INTO shifts VALUES ('hanako', true), ('ken', true)
"""


def prepare(dsn: str) -> None:
    reset_schema(dsn)
    with connect(dsn) as conn:
        for statement in SETUP_SQL.split(";\n"):
            conn.execute(statement)


def place_order(conn, product_id: int, quantity: int) -> None:
    """注文を登録し、在庫を減らす。2 つの更新は全部成功するか、全部なかったことになる。"""
    with conn.transaction():
        conn.execute("INSERT INTO orders (product_id, quantity) VALUES (%s, %s)", (product_id, quantity))
        conn.execute("UPDATE stock SET quantity = quantity - %s WHERE product_id = %s", (quantity, product_id))


def atomicity(dsn: str) -> tuple[int, int, str]:
    """在庫 5 に対して 9 個の注文を入れる。在庫の CHECK が失敗し、先に入れた注文の行も消える。"""
    prepare(dsn)
    with connect(dsn) as conn:
        try:
            place_order(conn, 1, 9)
            error = "成功"
        except psycopg.errors.CheckViolation as e:
            error = e.diag.constraint_name
        orders = conn.execute("SELECT count(*) FROM orders").fetchone()[0]
        stock = conn.execute("SELECT quantity FROM stock WHERE product_id = 1").fetchone()[0]
    return orders, stock, error


def take_day_off(conn, staff: str) -> bool:
    """店番が 2 人以上いるときだけ、自分の休みを登録する。SERIALIZABLE で動かす。"""
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        if conn.execute("SELECT count(*) FROM shifts WHERE on_duty").fetchone()[0] < 2:
            return False
        conn.execute("UPDATE shifts SET on_duty = false WHERE staff = %s", (staff,))
        return True


def retry(conn, func, *args, tries: int = 3):
    """直列化失敗（SQLSTATE 40001）なら、取引を最初からやり直す。"""
    for attempt in range(1, tries + 1):
        try:
            return func(conn, *args), attempt
        except psycopg.errors.SerializationFailure:
            if attempt == tries:
                raise


def write_skew_with_retry(dsn: str) -> tuple[list, int]:
    """2 人が同時に休みを申請する。片方は直列化失敗になり、やり直しで「1 人しかいない」と断られる。"""
    prepare(dsn)
    a, b = connect(dsn), connect(dsn)
    a.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
    b.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
    for conn in (a, b):
        conn.execute("SELECT count(*) FROM shifts WHERE on_duty")
    a.execute("UPDATE shifts SET on_duty = false WHERE staff = 'hanako'")
    b.execute("UPDATE shifts SET on_duty = false WHERE staff = 'ken'")
    a.execute("COMMIT")
    results = []
    try:
        b.execute("COMMIT")
    except psycopg.errors.SerializationFailure:
        b.execute("ROLLBACK")
        results.append(retry(b, take_day_off, "ken"))  # やり直し: 今度は hanako が休みなので断られる
    return results, a.execute("SELECT count(*) FROM shifts WHERE on_duty").fetchone()[0]


if __name__ == "__main__":
    import os

    print(atomicity(os.environ["PG_DSN"]))
    print(write_skew_with_retry(os.environ["PG_DSN"]))
