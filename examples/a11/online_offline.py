"""第11章: オフライン (学習用) とオンライン (推論用) の特徴量が食い違う原因を、再生して数えます。"""
from collections import defaultdict
from datetime import datetime, timedelta

import duckdb
import pyarrow as pa

from neboske_shop import generate

WINDOW_DAYS = 7
FIRST_T = datetime(2026, 1, 8)
LAST_T = datetime(2026, 6, 29)


def parse(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


class OnlineStore:
    """推論用の置き場の最小の実装。届いたイベントを顧客ごとに持ち、読むときに直近 7 日を数えます。
    同じ event_id は 2 回目以降を捨てます (届いた時点で分かる重複だけを除く)。"""

    def __init__(self):
        self.seen = set()
        self.by_customer = defaultdict(list)

    def apply(self, event):
        if event["event_id"] in self.seen:
            return
        self.seen.add(event["event_id"])
        self.by_customer[event["customer_id"]].append(parse(event["event_time"]))

    def read(self, customer_id, t):
        lo = t - timedelta(days=WINDOW_DAYS)
        return sum(1 for ts in self.by_customer[customer_id] if lo < ts <= t)


def read_grid(customers):
    """(顧客, 時刻) の全組。毎日 0 時に全顧客の値を読む想定です。"""
    days = (LAST_T - FIRST_T).days + 1
    return [(c, FIRST_T + timedelta(days=d)) for d in range(days) for c in customers]


def replay_online(events, grid):
    """イベントを届いた順 (received_at) に適用し、読む時刻 t までに届いたものだけで値を返します。"""
    ordered = sorted(events, key=lambda e: (e["received_at"], e["event_id"]))
    store, i, out = OnlineStore(), 0, {}
    for customer_id, t in sorted(grid, key=lambda g: (g[1], g[0])):
        while i < len(ordered) and parse(ordered[i]["received_at"]) <= t:
            store.apply(ordered[i])
            i += 1
        out[(customer_id, t)] = store.read(customer_id, t)
    return out


OFFLINE_SQL = {
    # 学習用に素直に書いた SQL: 発生時刻だけで数え、重複を除く
    "event_time_dedup": """
        SELECT g.customer_id, g.t, count(DISTINCT e.event_id) AS v FROM grid g
        LEFT JOIN events e ON e.customer_id = g.customer_id
         AND e.event_time > g.t - INTERVAL 7 DAY AND e.event_time <= g.t
        GROUP BY g.customer_id, g.t""",
    # 重複も除かない (二重に届いた分を 2 回数える)
    "no_dedup": """
        SELECT g.customer_id, g.t, count(e.event_id) AS v FROM grid g
        LEFT JOIN events e ON e.customer_id = g.customer_id
         AND e.event_time > g.t - INTERVAL 7 DAY AND e.event_time <= g.t
        GROUP BY g.customer_id, g.t""",
    # t の時点で届いていたものだけを数える (届いた時刻で条件を足す)
    "known_at_t": """
        SELECT g.customer_id, g.t, count(DISTINCT e.event_id) AS v FROM grid g
        LEFT JOIN events e ON e.customer_id = g.customer_id
         AND e.event_time > g.t - INTERVAL 7 DAY AND e.event_time <= g.t AND e.received_at <= g.t
        GROUP BY g.customer_id, g.t""",
}


def offline_values(con, name):
    return {(c, t): v for c, t, v in con.execute(OFFLINE_SQL[name]).fetchall()}


def load(events, grid):
    con = duckdb.connect()
    con.register("e_arrow", pa.Table.from_pylist(events))
    con.execute("""CREATE TABLE events AS SELECT event_id, customer_id,
                   CAST(event_time AS TIMESTAMP) AS event_time, CAST(received_at AS TIMESTAMP) AS received_at FROM e_arrow""")
    con.register("g_arrow", pa.Table.from_pylist([{"customer_id": c, "t": t} for c, t in grid]))
    con.execute("CREATE TABLE grid AS SELECT customer_id, t FROM g_arrow")
    return con


def skew(offline, online):
    """オフラインとオンラインで値が違う組の数と割合を返します。キーが違うときは失敗します。"""
    if offline.keys() != online.keys():
        raise ValueError("比べる組の集合が一致しません")
    diff = sum(1 for k in offline if offline[k] != online[k])
    return diff, diff / len(offline)


def run():
    data = generate()
    customers = sorted({c["customer_id"] for c in data["customers"]})
    grid = read_grid(customers)
    online = replay_online(data["events"], grid)
    con = load(data["events"], grid)
    return {name: skew(offline_values(con, name), online) for name in OFFLINE_SQL}, len(grid)
