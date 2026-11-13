"""制約（主キー・外部キー・一意・CHECK・NOT NULL）で、おかしなデータを入口で止めます。"""
import sys
from pathlib import Path

import psycopg

from b07_db import connect, reset_schema

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.common.neboske_shop import generate  # noqa: E402

SHOP_DDL = """
CREATE TABLE customers (
    customer_id int PRIMARY KEY,
    name        text NOT NULL,
    email       text UNIQUE,
    prefecture  text NOT NULL);
CREATE TABLE products (
    product_id int PRIMARY KEY,
    name       text NOT NULL,
    category   text NOT NULL,
    price      int NOT NULL CHECK (price > 0));
CREATE TABLE orders (
    order_id    int PRIMARY KEY,
    customer_id int NOT NULL REFERENCES customers,
    ordered_at  timestamp NOT NULL,
    status      text NOT NULL CHECK (status IN ('placed', 'shipped', 'delivered', 'cancelled')));
CREATE TABLE order_items (
    order_id   int REFERENCES orders,
    line_no    int,
    product_id int NOT NULL REFERENCES products,
    quantity   int NOT NULL CHECK (quantity > 0),
    unit_price int NOT NULL CHECK (unit_price > 0),
    PRIMARY KEY (order_id, line_no))
"""

SEED_SQL = """
INSERT INTO customers VALUES (1, '佐藤花子', 'hanako@example.com', '東京');
INSERT INTO products VALUES (1, '枕(標準)', '寝具', 3000);
INSERT INTO orders VALUES (1, 1, '2026-03-01 09:00:00', 'placed');
INSERT INTO order_items VALUES (1, 1, 1, 1, 3000)
"""

# 壊れた行を 1 つずつ入れて、どの制約が止めるかを見る。
BAD_STATEMENTS = {
    "主キーの重複": "INSERT INTO customers VALUES (1, '別人', 'other@example.com', '大阪')",
    "一意制約（メール）": "INSERT INTO customers VALUES (2, '別人', 'hanako@example.com', '大阪')",
    "NOT NULL": "INSERT INTO customers VALUES (3, NULL, 'x@example.com', '大阪')",
    "外部キー（存在しない顧客）": "INSERT INTO orders VALUES (2, 999, '2026-03-02 10:00:00', 'placed')",
    "CHECK（未知の状態）": "INSERT INTO orders VALUES (3, 1, '2026-03-02 10:00:00', 'SHIPPED')",
    "CHECK（数量が 0）": "INSERT INTO order_items VALUES (1, 2, 1, 0, 3000)",
}


def try_bad_statements(dsn: str) -> dict[str, str]:
    """各 SQL を実行し、止めた制約の種類（例外クラス名）を返します。"""
    reset_schema(dsn)
    result = {}
    with connect(dsn) as conn:
        for statement in SHOP_DDL.split(";\n"):
            conn.execute(statement)
        for statement in SEED_SQL.split(";\n"):
            conn.execute(statement)
        for label, sql in BAD_STATEMENTS.items():
            try:
                conn.execute(sql)
            except psycopg.Error as e:
                result[label] = type(e).__name__
    return result


def load_neboske_customers(dsn: str) -> str:
    """ねぼすけ商店の顧客をそのまま入れる。同じメールの二重登録で、一意制約が止める。"""
    reset_schema(dsn)
    customers = generate()["customers"]
    with connect(dsn) as conn:
        for statement in SHOP_DDL.split(";\n"):
            conn.execute(statement)
        with conn.cursor() as cur:
            for c in customers:
                try:
                    cur.execute("INSERT INTO customers VALUES (%(customer_id)s, %(name)s, %(email)s,"
                                " %(prefecture)s)", c)
                except psycopg.errors.UniqueViolation as e:
                    return f"customer_id={c['customer_id']}: {e.diag.message_primary} / {e.diag.message_detail}"
    return "全件入った"


if __name__ == "__main__":
    import os

    for label, error in try_bad_statements(os.environ["PG_DSN"]).items():
        print(f"{label}: {error}")
    print(load_neboske_customers(os.environ["PG_DSN"]))
