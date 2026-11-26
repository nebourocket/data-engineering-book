"""第8章: 毎日の読み込みの記録から、鮮度 (間に合ったか) と量 (行数が普通か) を監視します。"""
import random
import statistics
from datetime import date, datetime, timedelta

import duckdb

START = date(2026, 1, 1)
DAYS = 120
# 注入した事故: 日付の番号 → 種類。検知の当たり外れを数えるための正解です。
INCIDENTS = {40: "late", 55: "duplicate", 70: "partial", 85: "empty", 100: "late"}
WEEKDAY_FACTOR = {5: 0.6, 6: 0.5, 0: 1.1}  # 土 0.6・日 0.5・月 1.1・ほかは 1.0
DEADLINE_HOUR = 7  # FRESHNESS_SQL の INTERVAL 7 HOUR と同じ値


def make_load_log(seed=7):
    """毎朝の読み込みの記録 (日付・終わった時刻・行数) を作ります。揺らぎ付きの生成データで、事故を 5 日に入れます。"""
    rng = random.Random(seed)
    log = []
    for i in range(DAYS):
        day = START + timedelta(days=i)
        rows = round(2000 * WEEKDAY_FACTOR.get(day.weekday(), 1.0) * rng.gauss(1, 0.05))
        minutes = round(rng.gauss(330, 15))  # 5 時 30 分ごろ
        kind = INCIDENTS.get(i)
        if kind == "late":
            minutes = 550 if i == 40 else 460  # 9 時 10 分・7 時 40 分
        elif kind == "duplicate":
            rows *= 2
        elif kind == "partial":
            rows = round(rows * 0.3)
        elif kind == "empty":
            rows = 0
        finished = datetime(day.year, day.month, day.day) + timedelta(minutes=minutes)
        log.append({"d": day, "finished_at": finished, "row_count": rows})
    return log


def load_into_duckdb(log):
    con = duckdb.connect()
    con.execute("CREATE TABLE load_log (d DATE, finished_at TIMESTAMP, row_count INTEGER)")
    con.executemany("INSERT INTO load_log VALUES (?, ?, ?)", [(r["d"], r["finished_at"], r["row_count"]) for r in log])
    return con


FRESHNESS_SQL = """
SELECT d, finished_at FROM load_log
WHERE finished_at > d + INTERVAL 7 HOUR
ORDER BY d
"""


def naive_flags(rows, window=7, k=3):
    """直前 window 日の平均 ± k 標準偏差から外れた日の番号を返す。"""
    flagged = []
    for i in range(window, len(rows)):
        past = rows[i - window:i]
        mean, sd = statistics.mean(past), statistics.pstdev(past)
        if abs(rows[i] - mean) > k * sd:
            flagged.append(i)
    return flagged


def weekday_flags(rows, weeks=4, k=3, floor=0.2, skip=()):
    """同じ曜日の直前 weeks 週の中央値から、k x MAD (中央値からのずれの中央値) と floor 割のどちらか大きいほうを超えて外れた日の番号を返す。

    skip の日 (予定されたバックフィルなど) は、判定もしないし、基準にも使わない。基準が 3 日に満たないときは判定しない。
    """
    flagged = []
    for i in range(7 * weeks, len(rows)):
        if i in skip:
            continue
        past = [rows[i - 7 * w] for w in range(1, weeks + 1) if i - 7 * w not in skip]
        if len(past) < 3:
            continue
        med = statistics.median(past)
        mad = 1.4826 * statistics.median(abs(x - med) for x in past)
        if abs(rows[i] - med) > max(k * mad, floor * med):
            flagged.append(i)
    return flagged


def score(flagged, first_day):
    """量の事故 (late 以外) の正解と比べ、当たった日・見逃した日・誤報の数を返す。first_day より前は評価しない。"""
    truth = {i for i, kind in INCIDENTS.items() if kind != "late" and i >= first_day}  # late は量では見えない
    hit = truth & set(flagged)
    return {"detected": sorted(hit), "missed": sorted(truth - hit), "false_alarms": len([i for i in set(flagged) if i not in INCIDENTS and i >= first_day])}


BACKFILL_DAY = 90  # この日の読み込みで、直前 7 日ぶんを再読み込みした
LATE_DAY = 95      # この日のデータの 7 割は、翌日に届いた


def with_backfill_and_late_data(rows):
    """行数の列に、予定されたバックフィルと、遅れて届くデータを足したものを返す (元は変えない)。"""
    out = list(rows)
    out[BACKFILL_DAY] += sum(rows[BACKFILL_DAY - 7:BACKFILL_DAY])
    late = round(rows[LATE_DAY] * 0.7)
    out[LATE_DAY] -= late
    out[LATE_DAY + 1] += late
    return out
