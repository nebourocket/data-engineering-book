"""クエリベース CDC (updated_at で問い合わせる方式) が取りこぼす 3 つの場面を再現します。"""
import time

from neboske_shop import generate

SETUP = """
CREATE TABLE orders (
    order_id    integer PRIMARY KEY,
    customer_id integer NOT NULL,
    status      text    NOT NULL,
    amount      integer NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
)
"""


def load_orders(conn, n=200):
    """ねぼすけ商店の先頭 n 件の注文 (金額は明細の合計) を入れます。"""
    shop = generate()
    amount = {}
    for item in shop["order_items"]:
        amount[item["order_id"]] = amount.get(item["order_id"], 0) + item["quantity"] * item["unit_price"]
    conn.execute(SETUP)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO orders (order_id, customer_id, status, amount) VALUES (%s, %s, %s, %s)",
            [(o["order_id"], o["customer_id"], o["status"].lower(), amount[o["order_id"]])
             for o in shop["orders"][:n]])
    conn.commit()


def poll(conn, watermark):
    """updated_at が watermark より新しい行を読み、(行, 新しい watermark) を返します。"""
    rows = conn.execute(
        "SELECT order_id, status, updated_at FROM orders "
        "WHERE updated_at > %s::timestamptz ORDER BY updated_at", (watermark,)).fetchall()
    return rows, (rows[-1][2] if rows else watermark)


def run_scenario(box):
    """元の表に 5 回の変更をして、クエリベースが何を見られたかを返します。

    1. 注文 1 を shipped → delivered と 2 回更新する (ポーリングの間に 2 回)
    2. 注文 2 を削除する
    3. 注文 3 を更新するが、コミットは遅れる (長いトランザクション)
    4. 注文 4 を更新してコミットする
    """
    with box.connect() as setup:
        load_orders(setup)
    with box.connect() as slow, box.connect(autocommit=True) as fast, \
            box.connect(autocommit=True) as poller:
        first, mark = poll(poller, "-infinity")
        copy = {r[0]: r[1] for r in first}  # 倉庫側のコピー
        slow.execute("UPDATE orders SET status = 'cancelled', updated_at = now() WHERE order_id = 3")
        time.sleep(0.05)  # 上の now() は slow の開始時刻。fast はそれより後に始まる
        fast.execute("UPDATE orders SET status = 'shipped', updated_at = now() WHERE order_id = 1")
        fast.execute("UPDATE orders SET status = 'delivered', updated_at = now() WHERE order_id = 1")
        fast.execute("DELETE FROM orders WHERE order_id = 2")
        fast.execute("UPDATE orders SET status = 'shipped', updated_at = now() WHERE order_id = 4")
        second, mark = poll(poller, mark)
        slow.commit()  # 注文 3 の updated_at は mark より古いまま確定する
        third, mark = poll(poller, mark)
        copy.update({r[0]: r[1] for r in second + third})
        truth = dict(fast.execute("SELECT order_id, status FROM orders").fetchall())
    return {
        "initial_rows": len(first),
        "seen_after_changes": [(r[0], r[1]) for r in second],
        "seen_after_slow_commit": [(r[0], r[1]) for r in third],
        "wrong_rows": sorted(k for k in set(copy) | set(truth) if copy.get(k) != truth.get(k)),
    }
