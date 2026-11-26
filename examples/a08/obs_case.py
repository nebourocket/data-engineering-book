"""第8章のケーススタディ: 注文が増えたねぼすけ商店で、監視・SLO・リネージを組み合わせて事故を追います。"""
import statistics
import time

import duckdb
import pyarrow as pa

import slo_burn
from neboske_shop import generate


def detection_delays(firing_minutes, stalls):
    """各停止の開始から、最初に鳴るまでの分数。鳴らなかった停止は None。"""
    out = []
    for start, length in stalls:
        hits = [m for m in firing_minutes if start <= m < start + length + 120]
        out.append(min(hits) - start if hits else None)
    return out


def daily_count_seconds(scale, repeat=5):
    """注文を scale 倍に増やし、日別の件数を数える SQL (量の監視の元) を repeat 回測り、(行数, 日数, 秒数の中央値) を返す。"""
    orders = generate()["orders"]
    con = duckdb.connect()
    con.register("base_arrow", pa.Table.from_pylist(orders))
    con.execute(f"""CREATE TABLE orders AS
        SELECT o.order_id + k.k * 10000 AS order_id, o.ordered_at FROM base_arrow o, range({scale}) AS k(k)""")
    seconds = []
    for _ in range(repeat):
        start = time.perf_counter()
        days = con.execute("SELECT substr(ordered_at, 1, 10) AS d, count(*) FROM orders GROUP BY d").fetchall()
        seconds.append(time.perf_counter() - start)
    rows = con.execute("SELECT count(*) FROM orders").fetchone()[0]
    return rows, len(days), statistics.median(seconds)


def bad_samples(stall):
    """1 つの停止の間と、その後 2 時間のうちの、SLI が悪い測定回数と、最大の遅れ (分)。"""
    lag = slo_burn.build_lag([stall])
    start, length = stall
    window = range(start // slo_burn.STEP, (start + length + 120) // slo_burn.STEP)
    return sum(1 for i in window if lag[i] > slo_burn.LIMIT), max(lag[i] for i in window)


def run_alerts(stalls):
    """停止の一覧に対して SLO のアラート 4 種を動かし、{名前: (鳴った回数, 停止ごとの遅れ分)} を返す。"""
    bad = slo_burn.bad_flags(slo_burn.build_lag(stalls))
    result = {}
    for name, flags in slo_burn.alert_rules(bad).items():
        minutes = [i * slo_burn.STEP for i in slo_burn.firings(flags)]
        result[name] = (len(minutes), detection_delays(minutes, stalls))
    return result
