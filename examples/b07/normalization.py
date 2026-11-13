"""ねぼすけ商店の崩れた表を、第1〜第3正規形へ順に直します（PostgreSQL のスキーマ b07）。"""
from b07_db import connect, reset_schema

# 段階 0: 表計算ソフトから貼り付けたままの表。明細が 1 つのセルに入っている。
SHEET_DDL = """
CREATE TABLE sheet (
    order_id int, ordered_at timestamptz,
    customer_name text, customer_email text, customer_prefecture text,
    items text)
"""
SHEET_ROWS = [
    (1, "2026-03-01", "佐藤花子", "hanako@example.com", "東京", "枕(標準) x1, 毛布(大) x2"),
    (2, "2026-03-02", "佐藤花子", "hanako@example.com", "東京", "紅茶(標準) x3"),
    (3, "2026-03-02", "鈴木健", "ken@example.com", "石川", "枕(標準) x2"),
]

# 第1正規形: 1 行 = 1 注文明細。セルの中に複数の値を入れない。
FIRST_NF_DDL = """
CREATE TABLE orders_1nf (
    order_id int, line_no int, ordered_at timestamptz,
    customer_name text, customer_email text, customer_prefecture text,
    product_id int, product_name text, category text, unit_price numeric(12, 0), quantity int,
    PRIMARY KEY (order_id, line_no))
"""
FIRST_NF_ROWS = [
    (1, 1, "2026-03-01", "佐藤花子", "hanako@example.com", "東京", 1, "枕(標準)", "寝具", 3000, 1),
    (1, 2, "2026-03-01", "佐藤花子", "hanako@example.com", "東京", 2, "毛布(大)", "寝具", 5000, 2),
    (2, 1, "2026-03-02", "佐藤花子", "hanako@example.com", "東京", 3, "紅茶(標準)", "飲み物", 800, 3),
    (3, 1, "2026-03-02", "鈴木健", "ken@example.com", "石川", 1, "枕(標準)", "寝具", 3000, 2),
]

# 第2正規形: 主キー (order_id, line_no) の一部 order_id だけで決まる列を、注文の表へ出す。
SECOND_NF_DDL = """
CREATE TABLE orders_2nf (
    order_id int PRIMARY KEY, ordered_at timestamptz,
    customer_name text, customer_email text, customer_prefecture text);
CREATE TABLE order_items_2nf (
    order_id int REFERENCES orders_2nf, line_no int,
    product_id int, product_name text, category text, unit_price numeric(12, 0), quantity int,
    PRIMARY KEY (order_id, line_no))
"""

# 第3正規形: 主キー以外の列（customer_email、product_id）から決まる列を、さらに別の表へ出す。
THIRD_NF_DDL = """
CREATE TABLE customers (
    customer_id int PRIMARY KEY, name text, email text, prefecture text);
CREATE TABLE products (
    product_id int PRIMARY KEY, name text, category text);
CREATE TABLE orders (
    order_id int PRIMARY KEY, ordered_at timestamptz,
    customer_id int REFERENCES customers);
CREATE TABLE order_items (
    order_id int REFERENCES orders, line_no int,
    product_id int REFERENCES products, unit_price numeric(12, 0), quantity int,
    PRIMARY KEY (order_id, line_no))
"""

# 更新の異常: 第1正規形のまま、顧客のメールアドレスを直そうとして 1 行だけ更新してしまう。
UPDATE_ONE_ROW_SQL = """
UPDATE orders_1nf SET customer_email = 'hanako@neboske.example'
WHERE order_id = 1 AND line_no = 1
"""
EMAIL_VARIANTS_SQL = """
SELECT count(DISTINCT customer_email) FROM orders_1nf WHERE customer_name = '佐藤花子'
"""

# 第3正規形なら、メールアドレスの置き場所は 1 か所なので 1 回の更新で済む。
UPDATE_THIRD_NF_SQL = """
UPDATE customers SET email = 'hanako@neboske.example'
WHERE customer_id = 1
"""

# 意図的な非正規化: 分析用に、結合済みの幅広い表を別に作る（元の正規化された表は残す）。
WIDE_SQL = """
CREATE TABLE order_lines_wide AS
SELECT o.order_id, i.line_no, o.ordered_at, c.prefecture, p.category,
       i.quantity * i.unit_price AS sales
FROM orders AS o
JOIN customers AS c USING (customer_id)
JOIN order_items AS i USING (order_id)
JOIN products AS p USING (product_id)
"""


def run_stages(dsn: str) -> dict:
    """段階ごとに表を作って値を入れ、更新の異常と分割後の件数を返します。"""
    reset_schema(dsn)
    out = {}
    with connect(dsn) as conn:
        conn.execute(SHEET_DDL)
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO sheet VALUES (%s, %s, %s, %s, %s, %s)", SHEET_ROWS)
        conn.execute(FIRST_NF_DDL)
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO orders_1nf VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", FIRST_NF_ROWS)
        out["before"] = conn.execute(EMAIL_VARIANTS_SQL).fetchone()[0]
        conn.execute(UPDATE_ONE_ROW_SQL)
        out["after_partial_update"] = conn.execute(EMAIL_VARIANTS_SQL).fetchone()[0]

        conn.execute(SECOND_NF_DDL)
        conn.execute(THIRD_NF_DDL)
        conn.execute("INSERT INTO customers VALUES (1, '佐藤花子', 'hanako@example.com', '東京'),"
                     " (2, '鈴木健', 'ken@example.com', '石川')")
        conn.execute("INSERT INTO products VALUES (1, '枕(標準)', '寝具'),"
                     " (2, '毛布(大)', '寝具'), (3, '紅茶(標準)', '飲み物')")
        conn.execute("INSERT INTO orders VALUES (1, '2026-03-01', 1), (2, '2026-03-02', 1),"
                     " (3, '2026-03-02', 2)")
        conn.execute("INSERT INTO order_items VALUES (1, 1, 1, 3000, 1), (1, 2, 2, 5000, 2),"
                     " (2, 1, 3, 800, 3), (3, 1, 1, 3000, 2)")
        out["updated_rows"] = conn.execute(UPDATE_THIRD_NF_SQL).rowcount
        conn.execute(WIDE_SQL)
        out["wide"] = [(c, int(v)) for c, v in conn.execute(
            "SELECT category, sum(sales) FROM order_lines_wide GROUP BY category ORDER BY category").fetchall()]
        out["normalized"] = [(c, int(v)) for c, v in conn.execute(
            "SELECT p.category, sum(i.quantity * i.unit_price) FROM order_items AS i"
            " JOIN products AS p USING (product_id) GROUP BY p.category ORDER BY p.category").fetchall()]
    return out


if __name__ == "__main__":
    import os

    print(run_stages(os.environ["PG_DSN"]))
