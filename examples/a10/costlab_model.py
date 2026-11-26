"""費用の式と、使っていない計算資源の模型。単価はすべて例示用の仮の値です。"""
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Rates:
    """例示用の仮の単価です。実在の価格ではありません。請求の見積りには各社の価格ページの値を入れます。"""
    storage_per_gb_month: float = 0.02
    scan_per_tb: float = 5.0
    egress_per_gb: float = 0.09
    requests_per_1000: float = 0.0004
    compute_per_hour: float = 2.0


def monthly_cost(rates, *, storage_gb, scan_tb, egress_gb, requests, compute_hours):
    """月額を 5 つの費目に分け、合計と費目ごとの割合 (%) も返します。"""
    parts = {
        "storage": storage_gb * rates.storage_per_gb_month,
        "scan": scan_tb * rates.scan_per_tb,
        "egress": egress_gb * rates.egress_per_gb,
        "requests": requests / 1000 * rates.requests_per_1000,
        "compute": compute_hours * rates.compute_per_hour,
    }
    total = sum(parts.values())
    return {"parts": parts, "total": total, "share": {k: 100 * v / total for k, v in parts.items()}}


def query_starts(days=22, seed=7):
    """平日 22 日分の、クエリの開始時刻 (月初からの分)。毎時の定例 + 気まぐれな手動実行。"""
    rng = random.Random(seed)
    starts = []
    for d in range(days):
        base = d * 1440
        starts += [base + h * 60 for h in range(8, 19)]  # 8 時〜18 時に毎時 1 回
        starts += [base + rng.randrange(8 * 60, 20 * 60) for _ in range(6)]  # 手動実行 6 回
    return sorted(starts)


def billed_minutes(starts, run_minutes=2, suspend_after=None, total_minutes=30 * 1440):
    """自動停止の待ち時間ごとの課金分数。None は常時起動 (止めない) です。

    クエリが終わってから suspend_after 分、次が来なければ止まります。起動のたびに最低 1 分は課金されます。
    """
    if suspend_after is None:
        return total_minutes
    billed, up_until = 0, None  # up_until: いま起動している場合の、止まる予定の時刻
    for s in starts:
        stop_at = s + run_minutes + suspend_after
        if up_until is not None and s <= up_until:
            billed += max(0, stop_at - up_until)  # 動いている間に次が来たら、延びた分だけ足す
            up_until = max(up_until, stop_at)
        else:
            billed += max(1, run_minutes + suspend_after)  # 止まっていたら起動し直す
            up_until = stop_at
    return billed
