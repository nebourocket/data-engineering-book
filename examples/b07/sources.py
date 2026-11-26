"""ソースシステムが作るデータの形（更新で上書き / 追記のみ・4 つの時刻・ログ）。SQLite だけで動く。"""
import json
import re
import sqlite3


def update_in_place_vs_insert_only() -> dict:
    """同じ注文 1001 の状態変化を、上書きの表と追記だけの表に記録して比べる。"""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, status TEXT)")
    con.execute("CREATE TABLE order_status_log (order_id INTEGER, status TEXT, changed_at TEXT)")
    steps = [("注文済", "2026-11-01 09:00"), ("発送済", "2026-11-02 15:00"), ("配達済", "2026-11-04 11:00")]
    for i, (status, at) in enumerate(steps):
        if i == 0:
            con.execute("INSERT INTO orders VALUES (1001, ?)", (status,))
        else:
            con.execute("UPDATE orders SET status = ? WHERE order_id = 1001", (status,))  # 上書き
        con.execute("INSERT INTO order_status_log VALUES (1001, ?, ?)", (status, at))  # 追記のみ
    in_place = con.execute("SELECT * FROM orders").fetchall()
    history = con.execute("SELECT status, changed_at FROM order_status_log ORDER BY changed_at").fetchall()
    # 11/3 の終わりの状態は、追記のみの表なら再現できる
    on_nov3 = con.execute(
        "SELECT status FROM order_status_log WHERE order_id = 1001 AND changed_at < '2026-11-04' "
        "ORDER BY changed_at DESC LIMIT 1").fetchone()[0]
    latest = con.execute(
        "SELECT order_id, status FROM (SELECT *, ROW_NUMBER() OVER "
        "(PARTITION BY order_id ORDER BY changed_at DESC) AS rn FROM order_status_log) WHERE rn = 1"
    ).fetchall()
    return {"in_place": in_place, "history": history, "on_nov3": on_nov3, "latest": latest}


# (event_id, 起きた時刻, ソースが書いた時刻, 取り込んだ時刻)
EVENTS = [
    (1, "2026-11-01 10:00", "2026-11-01 10:00", "2026-11-02 02:00"),
    (2, "2026-11-01 23:50", "2026-11-01 23:50", "2026-11-02 02:00"),
    (3, "2026-11-02 00:10", "2026-11-02 00:10", "2026-11-02 02:00"),
    (4, "2026-11-02 09:00", "2026-11-02 09:00", "2026-11-03 02:00"),
    (5, "2026-11-01 22:30", "2026-11-02 08:00", "2026-11-03 02:00"),  # スマホが圏外で、翌朝まとめて送られた
    (6, "2026-11-02 18:00", "2026-11-02 18:00", "2026-11-03 02:00"),
]


def daily_counts_by_each_time() -> dict:
    """同じ 6 件を、どの時刻で日付を切るかで数え直す。"""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE ev (event_id INTEGER, event_time TEXT, written_at TEXT, ingested_at TEXT)")
    con.executemany("INSERT INTO ev VALUES (?, ?, ?, ?)", EVENTS)
    out = {}
    for col in ("event_time", "written_at", "ingested_at"):
        out[col] = con.execute(
            f"SELECT date({col}) AS d, COUNT(*) FROM ev GROUP BY d ORDER BY d").fetchall()
    return out


APACHE_LINE = '203.0.113.7 - - [02/Nov/2026:09:00:01 +0900] "GET /products/52 HTTP/1.1" 200 5120'
APACHE_RE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+) [^"]*" (\d{3}) (\d+)$')
JSON_LINE = '{"ts": "2026-11-02T09:00:01+09:00", "level": "INFO", "msg": "order_created", "order_id": 1001}'


def parse_logs() -> dict:
    """文字列のログは正規表現で切り出し、JSON のログは読むだけで列になる。"""
    ip, _, _, path, status, _ = APACHE_RE.match(APACHE_LINE).groups()
    unstructured = {"ip": ip, "path": path, "status": int(status)}
    structured = json.loads(JSON_LINE)
    return {"unstructured": unstructured, "structured": structured}


if __name__ == "__main__":
    print(update_in_place_vs_insert_only())
    print(daily_counts_by_each_time())
    print(parse_logs())
