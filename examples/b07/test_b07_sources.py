"""sources.py の数字を固定する。SQLite だけで動くので PostgreSQL は要らない。"""
import sources


def test_update_in_place_loses_history():
    r = sources.update_in_place_vs_insert_only()
    assert r["in_place"] == [(1001, "配達済")]
    assert r["history"] == [("注文済", "2026-11-01 09:00"), ("発送済", "2026-11-02 15:00"), ("配達済", "2026-11-04 11:00")]
    assert r["on_nov3"] == "発送済"
    assert r["latest"] == [(1001, "配達済")]


def test_daily_counts_depend_on_which_time():
    c = sources.daily_counts_by_each_time()
    assert c["event_time"] == [("2026-11-01", 3), ("2026-11-02", 3)]
    assert c["written_at"] == [("2026-11-01", 2), ("2026-11-02", 4)]
    assert c["ingested_at"] == [("2026-11-02", 3), ("2026-11-03", 3)]


def test_parse_logs():
    r = sources.parse_logs()
    assert r["unstructured"] == {"ip": "203.0.113.7", "path": "/products/52", "status": 200}
    assert r["structured"]["order_id"] == 1001


def test_nov1_has_two_events_until_ingested_on_nov3():
    # event_time が 11/1 の件数は、取り込み前 (11/3 の朝まで) は 2 件、取り込み後は 3 件
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE ev (event_id INTEGER, event_time TEXT, written_at TEXT, ingested_at TEXT)")
    con.executemany("INSERT INTO ev VALUES (?, ?, ?, ?)", sources.EVENTS)
    q = "SELECT COUNT(*) FROM ev WHERE date(event_time) = '2026-11-01' AND ingested_at < ?"
    assert con.execute(q, ("2026-11-03",)).fetchone()[0] == 2
    assert con.execute(q, ("2026-11-04",)).fetchone()[0] == 3
