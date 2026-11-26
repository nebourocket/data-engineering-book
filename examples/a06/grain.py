"""粒度の混在の罠: 注文単位の送料を、明細単位のワイドテーブルで足すと何が起きるか。"""


def shipping_by_method(con):
    """キャンセルを除いた送料の合計を、5 通りの書き方で出します (正しい値は orders から直接足した値)。"""
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "orders (正しい)": q("SELECT sum(shipping_fee) FROM orders WHERE status <> 'cancelled'"),
        "obt の単純な合計": q("SELECT sum(shipping_fee) FROM obt_sales WHERE status <> 'cancelled'"),
        "obt の SUM(DISTINCT)": q("SELECT sum(DISTINCT shipping_fee) FROM obt_sales WHERE status <> 'cancelled'"),
        "obt を注文で重複排除": q("SELECT sum(shipping_fee) FROM (SELECT DISTINCT order_id, shipping_fee "
                                 "FROM obt_sales WHERE status <> 'cancelled')"),
        "obt の先頭明細だけ": q("SELECT sum(shipping_fee) FROM obt_sales WHERE status <> 'cancelled' AND line_no = 1"),
    }


def average_order_value(con):
    """平均注文額: 明細の平均 (誤り) と、注文ごとに合計してから平均 (正しい)。"""
    per_line = con.execute("SELECT avg(amount) FROM obt_sales WHERE status <> 'cancelled'").fetchone()[0]
    per_order = con.execute(
        "SELECT avg(total) FROM (SELECT order_id, sum(amount) AS total FROM obt_sales "
        "WHERE status <> 'cancelled' GROUP BY order_id)").fetchone()[0]
    return {"明細の平均": round(per_line, 1), "注文の平均": round(per_order, 1)}
