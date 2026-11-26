"""二重書き込みの問題と、outbox パターン (同じトランザクションで outbox に書き、別の工程が送る)。"""
import json
import random

SETUP = """
CREATE TABLE orders (order_id integer PRIMARY KEY, customer_id integer NOT NULL, amount integer NOT NULL);
CREATE TABLE outbox (
    id           bigserial PRIMARY KEY,
    aggregate_id integer NOT NULL,
    event_type   text    NOT NULL,
    payload      jsonb   NOT NULL,
    sent_at      timestamptz
)
"""


class Broker:
    """メッセージの届け先の代わりです。失敗は呼び出し側が決めた順番で起こします。"""

    def __init__(self):
        self.messages = []

    def publish(self, topic, message):
        self.messages.append((topic, message))


def dual_write(conn, broker, order_id, amount, crash):
    """二重書き込み: DB にコミットしてから、別にメッセージを送ります。

    crash が "between" ならコミットのあと送る前に落ちた想定で、メッセージは失われます。
    """
    conn.execute("INSERT INTO orders VALUES (%s, 1, %s)", (order_id, amount))
    conn.commit()
    if crash == "between":
        raise RuntimeError("コミットの後、送信の前にプロセスが落ちた")
    broker.publish("orders", json.dumps({"order_id": order_id, "amount": amount}))


def dual_write_publish_first(conn, broker, order_id, amount, rollback):
    """順番を逆にした二重書き込み: 先に送ってから DB に書きます。DB が失敗すると幻のメッセージが残ります。"""
    broker.publish("orders", json.dumps({"order_id": order_id, "amount": amount}))
    conn.execute("INSERT INTO orders VALUES (%s, 1, %s)", (order_id, amount))
    if rollback:
        conn.rollback()
        raise RuntimeError("DB への書き込みが失敗した")
    conn.commit()


def place_order(conn, order_id, amount, fail=False):
    """outbox パターン: 注文と、注文が入ったというイベントを 1 つのトランザクションで書きます。

    fail が真なら、2 つの書き込みのあと、コミットの前に失敗します (どちらも残りません)。
    """
    with conn.transaction():
        conn.execute("INSERT INTO orders VALUES (%s, 1, %s)", (order_id, amount))
        conn.execute(
            "INSERT INTO outbox (aggregate_id, event_type, payload) VALUES (%s, 'OrderPlaced', %s::jsonb)",
            (order_id, json.dumps({"order_id": order_id, "amount": amount})))
        if fail:
            raise RuntimeError("コミットの前に落ちた")


def relay_once(conn, broker, batch=100, crash_after=None):
    """未送信の行を送って、送信済みの印を付けます。何度呼んでも、送り漏らしはありません。

    FOR UPDATE SKIP LOCKED は、ほかの中継役が掴んでいる行を飛ばします。
    crash_after 件送ったところで落ちると、印が付かないので次の回で同じ行を送り直します。
    """
    with conn.transaction():
        rows = conn.execute(
            "SELECT id, aggregate_id, payload FROM outbox WHERE sent_at IS NULL "
            "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED", (batch,)).fetchall()
        for sent, (row_id, aggregate_id, payload) in enumerate(rows):
            if crash_after is not None and sent == crash_after:
                raise RuntimeError("中継役が送信の途中で落ちた")
            broker.publish("orders", json.dumps({"event_id": row_id, "aggregate_id": aggregate_id,
                                                 **payload}))
            conn.execute("UPDATE outbox SET sent_at = now() WHERE id = %s", (row_id,))
    return len(rows)


def failure_plan(n, rate, seed=7):
    """n 件のうち、どの注文で失敗を起こすかを決めます (同じ seed なら同じ結果)。"""
    rng = random.Random(seed)
    return {i for i in range(n) if rng.random() < rate}


def compare(box, n=1000, rate=0.05):
    """同じ失敗の計画 (n 件のうち約 rate の割合) を 3 つの書き方に当てて、食い違いを数えます。"""
    bad = failure_plan(n, rate)
    result = {"failures_injected": len(bad)}
    with box.connect() as conn:
        conn.execute(SETUP)
        conn.commit()

        broker = Broker()
        for i in range(n):
            try:
                dual_write(conn, broker, i, 100, "between" if i in bad else None)
            except RuntimeError:
                pass
        db_rows = conn.execute("SELECT count(*) FROM orders").fetchone()[0]
        result["dual_write_commit_first"] = {"orders": db_rows, "messages": len(broker.messages),
                                             "lost_events": db_rows - len(broker.messages)}

        conn.execute("TRUNCATE orders")
        conn.commit()
        broker = Broker()
        for i in range(n):
            try:
                dual_write_publish_first(conn, broker, i, 100, i in bad)
            except RuntimeError:
                pass
        db_rows = conn.execute("SELECT count(*) FROM orders").fetchone()[0]
        result["dual_write_publish_first"] = {"orders": db_rows, "messages": len(broker.messages),
                                              "phantom_events": len(broker.messages) - db_rows}

        conn.execute("TRUNCATE orders")
        conn.commit()
        for i in range(n):
            try:
                place_order(conn, i, 100, fail=i in bad)
            except RuntimeError:
                pass
        conn.commit()
        broker = Broker()
        try:
            relay_once(conn, broker, batch=n, crash_after=n // 2)  # 途中で落ちる
        except RuntimeError:
            pass
        while relay_once(conn, broker, batch=n):  # 再起動後の回
            pass
        db_rows = conn.execute("SELECT count(*) FROM orders").fetchone()[0]
        ids = [json.loads(m)["event_id"] for _, m in broker.messages]
        result["outbox"] = {"orders": db_rows, "messages": len(ids), "distinct_events": len(set(ids)),
                            "lost_events": db_rows - len(set(ids)), "duplicates": len(ids) - len(set(ids))}
    return result


def relay_in_parallel(box, workers=4, rows=400, batch=50):
    """中継役を workers 本 (それぞれ別の接続) 同時に動かして、重複と送り漏れが無いことを数えます。"""
    from concurrent.futures import ThreadPoolExecutor

    with box.connect() as conn:
        conn.execute(SETUP)
        for i in range(rows):
            place_order(conn, i, 100)
        conn.commit()
    broker = Broker()

    def worker(_):
        sent = 0
        with box.connect() as c:
            while True:
                n = relay_once(c, broker, batch=batch)
                sent += n
                if n == 0:
                    return sent

    with ThreadPoolExecutor(workers) as pool:
        per_worker = list(pool.map(worker, range(workers)))
    ids = [json.loads(m)["event_id"] for _, m in broker.messages]
    return {"messages": len(ids), "distinct": len(set(ids)), "per_worker_sum": sum(per_worker)}
