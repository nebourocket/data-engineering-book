"""順序の入れ替わりと重複に耐える消費者、イベントの 2 つの形、イベントソーシングの最小例。"""
import json
import random

STATUSES = ["placed", "paid", "shipped", "delivered"]


def make_state_events(n_orders=500, seed=3):
    """注文ごとに version 1..4 の「状態の転送」イベントを作ります (event_id は全体で一意)。"""
    events, event_id = [], 0
    for order_id in range(1, n_orders + 1):
        for version, status in enumerate(STATUSES, start=1):
            event_id += 1
            events.append({"event_id": event_id, "order_id": order_id, "version": version,
                           "status": status})
    return events


def deliver(events, seed=11, duplicate_rate=0.1, window=8):
    """届き方を荒くします: window 件の中で順番を入れ替え、duplicate_rate の割合を 2 回届けます。"""
    rng = random.Random(seed)
    out = []
    for start in range(0, len(events), window):
        chunk = list(events[start:start + window])
        rng.shuffle(chunk)
        for event in chunk:
            out.append(event)
            if rng.random() < duplicate_rate:
                out.append(event)
    return out


STATE_SETUP = """
CREATE TABLE IF NOT EXISTS order_state (order_id integer PRIMARY KEY, version integer NOT NULL, status text NOT NULL);
CREATE TABLE IF NOT EXISTS inbox (event_id bigint PRIMARY KEY);
CREATE TABLE IF NOT EXISTS loyalty (customer_id integer PRIMARY KEY, points integer NOT NULL DEFAULT 0)
"""


def apply_last_write_wins(conn, event):
    """届いた順に上書きします。順序が入れ替わると古い状態が勝ちます。"""
    conn.execute(
        "INSERT INTO order_state VALUES (%(order_id)s, %(version)s, %(status)s) "
        "ON CONFLICT (order_id) DO UPDATE SET version = EXCLUDED.version, status = EXCLUDED.status",
        event)


def apply_version_guard(conn, event):
    """version が新しいときだけ上書きします。重複にも順序の入れ替わりにも強い、冪等な書き方です。"""
    conn.execute(
        "INSERT INTO order_state VALUES (%(order_id)s, %(version)s, %(status)s) "
        "ON CONFLICT (order_id) DO UPDATE SET version = EXCLUDED.version, status = EXCLUDED.status "
        "WHERE order_state.version < EXCLUDED.version",
        event)


def apply_points_once(conn, event):
    """加算のイベント: 受信済みの印 (inbox) と加算を同じトランザクションで行います。"""
    with conn.transaction():
        first_time = conn.execute(
            "INSERT INTO inbox VALUES (%(event_id)s) ON CONFLICT DO NOTHING RETURNING 1", event).fetchone()
        if first_time:
            conn.execute(
                "INSERT INTO loyalty VALUES (%(customer_id)s, %(points)s) "
                "ON CONFLICT (customer_id) DO UPDATE SET points = loyalty.points + EXCLUDED.points", event)


def apply_points_blindly(conn, event):
    """印を付けずに加算します。同じイベントが 2 回届くと 2 回足されます。"""
    conn.execute(
        "INSERT INTO loyalty VALUES (%(customer_id)s, %(points)s) "
        "ON CONFLICT (customer_id) DO UPDATE SET points = loyalty.points + EXCLUDED.points", event)


def wrong_states(conn, events):
    """正しい最終状態 (各注文の最大 version) と違う注文の数を返します。"""
    expected = {}
    for e in events:
        if e["version"] > expected.get(e["order_id"], (0, ""))[0]:
            expected[e["order_id"]] = (e["version"], e["status"])
    got = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT * FROM order_state").fetchall()}
    return sum(1 for k, v in expected.items() if got.get(k) != v)


def run_state_consumers(box, n_orders=500):
    events = make_state_events(n_orders)
    arrived = deliver(events)
    out = {"events": len(events), "delivered": len(arrived)}
    with box.connect() as conn:
        conn.execute(STATE_SETUP)
        for name, apply in [("last_write_wins", apply_last_write_wins),
                            ("version_guard", apply_version_guard)]:
            conn.execute("TRUNCATE order_state")
            for e in arrived:
                apply(conn, e)
            out[name] = {"wrong_orders": wrong_states(conn, events)}
        conn.commit()
    return out


def run_points_consumers(box, n_events=300, seed=5):
    """加算イベントを 2 回ずつ混ぜて届け、合計のずれを測ります。"""
    rng = random.Random(seed)
    events = [{"event_id": i, "customer_id": 1 + i % 10, "points": rng.randint(1, 5)}
              for i in range(1, n_events + 1)]
    arrived = deliver(events, duplicate_rate=0.1)
    truth = sum(e["points"] for e in events)
    out = {"events": n_events, "delivered": len(arrived), "true_total": truth}
    with box.connect() as conn:
        conn.execute(STATE_SETUP)
        for name, apply in [("blind", apply_points_blindly), ("inbox", apply_points_once)]:
            conn.execute("TRUNCATE loyalty, inbox")
            for e in arrived:
                apply(conn, e)
            out[name] = conn.execute("SELECT sum(points) FROM loyalty").fetchone()[0]
        conn.commit()
    return out


def notification_vs_state(changes):
    """同じ注文の変更列を、通知型と状態の転送型で流したときに、消費者が見られる状態を比べます。

    通知型: 「注文 7 が変わった」だけを送り、消費者が元に問い合わせて今の状態を読む。
    状態の転送型: 変更後の状態そのものをイベントに入れる。
    """
    source = {}  # 元のデータベース (最後の状態だけ持つ)
    notices, carried = [], []
    for order_id, status in changes:
        source[order_id] = status
        notices.append({"order_id": order_id})
        carried.append({"order_id": order_id, "status": status})
    lookups = 0
    seen_by_notice = []
    for notice in notices:  # 消費者は後から通知を処理する。その時点の元の状態を読む
        lookups += 1
        seen_by_notice.append(source[notice["order_id"]])
    return {"notice_seen": seen_by_notice, "carried_seen": [c["status"] for c in carried],
            "lookups_needed": lookups,
            "bytes_notice": sum(len(json.dumps(n)) for n in notices),
            "bytes_carried": sum(len(json.dumps(c)) for c in carried)}


def fold(events):
    """イベントソーシング: 状態は持たず、イベントの列から現在の状態を組み立てます。"""
    state = {}
    for e in events:
        if e["type"] == "OrderPlaced":
            state[e["order_id"]] = {"status": "placed", "amount": e["amount"]}
        elif e["type"] == "OrderShipped":
            state[e["order_id"]]["status"] = "shipped"
        elif e["type"] == "OrderCancelled":
            state[e["order_id"]]["status"] = "cancelled"
    return state
