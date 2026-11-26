"""イベント時刻・ウォーターマーク・状態を、Kafka も Spark も使わずに再現する小さな模型。

時間はすべて「秒」の整数です。処理側の時計は、イベントが届いた時刻 (arrival) で進みます。
同じ引数なら同じ結果になるので、表の数字をそのままテストで確かめられます。
"""
import copy
import random
import sqlite3
from dataclasses import dataclass, replace

CATEGORIES = ["寝具", "目覚まし", "飲み物", "朝食", "雑貨"]
MODELS = ["fast", "mixed", "long_tail", "mobile"]


@dataclass(frozen=True)
class Event:
    event_id: int
    category: str
    event_time: int  # 起きた時刻
    arrival: int     # 処理側に届いた時刻


def sample_delay(rng, model):
    """遅れ (秒) を 1 つ引きます。分布の形が違うだけで、平均はそろえていません。"""
    if model == "fast":
        return rng.expovariate(1 / 2)
    if model == "mixed":
        return rng.expovariate(1 / 3) if rng.random() < 0.9 else rng.expovariate(1 / 90)
    if model == "long_tail":
        return rng.lognormvariate(2.0, 1.3)
    if model == "mobile":
        return rng.expovariate(1 / 3) if rng.random() < 0.95 else rng.uniform(300, 900)
    raise ValueError(model)


def make_events(model, n=6000, span=3600, seed=7):
    """span 秒の間に起きた n 件の閲覧イベントを作り、届いた順に並べて返します。"""
    rng = random.Random(seed)
    times = sorted(int(rng.uniform(0, span)) for _ in range(n))
    events = [Event(i, rng.choice(CATEGORIES), t, t + int(sample_delay(rng, model)))
              for i, t in enumerate(times)]
    return sorted(events, key=lambda e: (e.arrival, e.event_id))


def tumbling_start(t, size):
    """タンブリングウィンドウ: どの時刻も、ちょうど 1 つの窓に入ります。"""
    return t // size * size


def sliding_starts(t, size, slide):
    """スライディングウィンドウ: 時刻 t を含む窓の開始時刻すべて (size/slide 個)。"""
    last = t // slide * slide
    return list(range(last - size + slide, last + 1, slide))


def sessionize(times, gap):
    """セッションウィンドウ: 前のイベントから gap 秒より空いたら、新しいセッションにします。"""
    sessions = []
    for t in sorted(times):
        if sessions and t - sessions[-1][1] <= gap:
            sessions[-1][1] = t
            sessions[-1][2] += 1
        else:
            sessions.append([t, t, 1])
    return [tuple(s) for s in sessions]


class WindowAggregator:
    """カテゴリ別・窓別の件数を数え、ウォーターマークを過ぎた窓を確定して出力します。"""

    def __init__(self, size=60, lateness=0):
        self.size, self.lateness = size, lateness
        self.state = {}            # (窓の開始, カテゴリ) -> 件数
        self.max_event_time = -1
        self.dropped = 0
        self.peak_state = 0

    def watermark(self):
        return self.max_event_time - self.lateness

    def process(self, event):
        """1 件を処理し、確定した行 (窓の開始, カテゴリ, 件数, 確定した時刻) のリストを返します。"""
        start = tumbling_start(event.event_time, self.size)
        if start + self.size <= self.watermark():
            self.dropped += 1  # 窓はもう確定済み: 遅すぎて捨てる
            return []
        key = (start, event.category)
        self.state[key] = self.state.get(key, 0) + 1
        self.max_event_time = max(self.max_event_time, event.event_time)
        self.peak_state = max(self.peak_state, len(self.state))
        closed = [k for k in self.state if k[0] + self.size <= self.watermark()]
        return [(k[0], k[1], self.state.pop(k), event.arrival) for k in sorted(closed)]

    def flush(self, clock):
        """入力が終わったとき、残りの窓をすべて確定します。"""
        rows = [(k[0], k[1], n, clock) for k, n in sorted(self.state.items())]
        self.state.clear()
        return rows

    def snapshot(self):
        return copy.deepcopy(self.__dict__)

    def restore(self, snapshot):
        self.__dict__ = copy.deepcopy(snapshot)


def truth(events, size=60):
    """全部の行が揃ってから数えた「正解」。"""
    counts = {}
    for e in events:
        key = (tumbling_start(e.event_time, size), e.category)
        counts[key] = counts.get(key, 0) + 1
    return counts


def cell_errors(expected, got):
    """セルごとの相対誤差 |出力 - 正解| / 正解 (出力に無いセルは 1.0) と、合計の取りこぼし (%)。"""
    errors = sorted(abs(got.get(k, 0) - n) / n for k, n in expected.items())
    at = lambda q: errors[int(q * (len(errors) - 1))]  # noqa: E731
    missing = 100 * (sum(expected.values()) - sum(got.values())) / sum(expected.values())
    return {"rel_err_median": at(0.5), "rel_err_p95": at(0.95), "missing_total_pct": missing}


def evaluate(events, lateness, size=60):
    """ウォーターマークの長さを決めて流し、捨てた行・誤った集計・誤差の大きさ・確定の遅れ・状態の大きさを測ります。"""
    agg = WindowAggregator(size, lateness)
    rows = []
    for e in events:
        rows += agg.process(e)
    delays = sorted(clock - (s + size) for s, _, _, clock in rows)  # 入力の終わりでの確定は含めません
    rows += agg.flush(events[-1].arrival)
    expected = truth(events, size)
    got = {(s, c): n for s, c, n, _ in rows}
    wrong = sum(1 for k, n in expected.items() if got.get(k) != n)
    return {
        "dropped_pct": 100 * agg.dropped / len(events),
        "wrong_cells_pct": 100 * wrong / len(expected),
        **cell_errors(expected, got),
        "delay_mean": sum(delays) / len(delays),
        "delay_p95": delays[int(0.95 * (len(delays) - 1))],
        "peak_state": agg.peak_state,
        "output_rows": len(rows),
    }


def three_tiers(events, fast_s=30, confirmed_s=300, size=60):
    """3 層の設計を動かします。ダッシュボード (短い猶予) と確定 (長い猶予) の誤差を測り、夜のバッチで確定の表を上書きします。"""
    expected = truth(events, size)
    out = {}
    tables = {}
    for name, lateness in (("dashboard", fast_s), ("confirmed", confirmed_s)):
        agg = WindowAggregator(size, lateness)
        db = make_sink(idempotent=True)
        for e in events:
            for s, c, n, _ in agg.process(e):
                write_row(db, (s, c, n), True)
        for s, c, n, _ in agg.flush(events[-1].arrival):
            write_row(db, (s, c, n), True)
        tables[name] = db
        out[name] = cell_errors(expected, {(s, c): n for s, c, n in db.execute("SELECT * FROM out")})
    for (s, c), n in expected.items():  # 夜のバッチ: 全部揃ったデータの正しい値で、主キーを上書きする
        write_row(tables["confirmed"], (s, c, n), True)
    out["nightly"] = cell_errors(expected, {(s, c): n for s, c, n in tables["confirmed"].execute("SELECT * FROM out")})
    return out


def make_sink(idempotent):
    """本物の出力先 (SQLite)。冪等版は (窓の開始, カテゴリ) を主キーにして INSERT OR REPLACE、単純な追記版は主キーなしの INSERT。"""
    db = sqlite3.connect(":memory:")
    if idempotent:
        db.execute("CREATE TABLE out (start INT, category TEXT, n INT, PRIMARY KEY (start, category))")
    else:
        db.execute("CREATE TABLE out (start INT, category TEXT, n INT)")
    return db


def write_row(db, row, idempotent):
    verb = "INSERT OR REPLACE" if idempotent else "INSERT"
    db.execute(f"{verb} INTO out VALUES (?, ?, ?)", row)


def run_with_crash(events, lateness, crash_at, checkpoint_every, idempotent):
    """途中で落ちて、最後のチェックポイントから再開します。出力先 (SQLite) が単純な追記か、主キーで上書きかを比べます。"""
    agg = WindowAggregator(60, lateness)
    db = make_sink(idempotent)
    checkpoint = (0, agg.snapshot())
    crashed = False
    i = 0
    while i < len(events):
        if i % checkpoint_every == 0:
            checkpoint = (i, agg.snapshot())
        if i == crash_at and not crashed:
            crashed = True
            i = checkpoint[0]          # 位置も状態も、チェックポイントの時点まで戻る (出力先の書き込みは戻らない)
            agg.restore(checkpoint[1])
            continue
        for s, c, n, _ in agg.process(events[i]):
            write_row(db, (s, c, n), idempotent)
        i += 1
    for s, c, n, _ in agg.flush(events[-1].arrival):
        write_row(db, (s, c, n), idempotent)
    return db.execute("SELECT start, category, n FROM out ORDER BY start, category, n").fetchall()


def crash_sweep(events, lateness=60, checkpoint_every=1000, crash_points=range(500, 6000, 500)):
    """落ちる位置を変えながら、追記版と冪等版が、落ちなかった場合と同じ結果になるかを数えます。"""
    clean = run_with_crash(events, lateness, 10**9, checkpoint_every, idempotent=True)
    plain_extra = []
    idem_same = 0
    for point in crash_points:
        plain = run_with_crash(events, lateness, point, checkpoint_every, idempotent=False)
        plain_extra.append(len(plain) - len(clean))
        idem_same += run_with_crash(events, lateness, point, checkpoint_every, idempotent=True) == clean
    return {"crash_points": len(crash_points), "clean_rows": len(clean), "plain_extra_rows": plain_extra,
            "plain_with_duplicates": sum(1 for x in plain_extra if x > 0), "idempotent_same": idem_same}


def backlog_after(arrivals_per_s, capacity_per_s, seconds):
    """バックプレッシャーの一番単純な見積もり: 入る速さが処理より速い間、滞留は 1 秒ごとに差の分だけ増えます。"""
    return max(0, (arrivals_per_s - capacity_per_s) * seconds)


def seconds_to_drain(backlog, arrivals_per_s, capacity_per_s):
    """滞留を捌き切るまでの秒数。処理の余力 (capacity - arrivals) がゼロ以下なら、永久に終わりません。"""
    spare = capacity_per_s - arrivals_per_s
    return None if spare <= 0 else backlog / spare


def delay_stats(events):
    """遅れ (arrival - event_time) の中央値・99 パーセンタイル・最大と、届いた順で時刻が戻った件数の割合。"""
    delays = sorted(e.arrival - e.event_time for e in events)
    at = lambda q: delays[int(q * (len(delays) - 1))]  # noqa: E731
    backwards = sum(1 for a, b in zip(events, events[1:]) if b.event_time < a.event_time)
    return {"p50": at(0.5), "p99": at(0.99), "max": delays[-1],
            "out_of_order_pct": 100 * backwards / (len(events) - 1)}


SAMPLE = [(10, 12), (65, 66), (30, 70), (70, 71), (50, 130), (200, 201)]


def walkthrough(lateness=10, size=60):
    """小さな例で、1 件ずつウォーターマークと窓がどう動くかを記録します (event_time, arrival)。"""
    agg = WindowAggregator(size, lateness)
    rows = []
    for i, (event_time, arrival) in enumerate(SAMPLE):
        before = agg.watermark()
        dropped = agg.dropped
        closed = agg.process(Event(i, "寝具", event_time, arrival))
        rows.append({"event_time": event_time, "arrival": arrival, "watermark_before": before,
                     "action": "捨てた" if agg.dropped > dropped else "数えた",
                     "closed": [(s, n) for s, _, n, _ in closed]})
    return rows


def update_rows(events, lateness, trigger=10, size=60):
    """更新モードの出力行数: trigger 秒ごとに、その間に変わった (窓, カテゴリ) を 1 行ずつ出します。"""
    agg = WindowAggregator(size, lateness)
    changed, total = set(), 0
    tick = events[0].arrival // trigger
    for e in events:
        if e.arrival // trigger != tick:
            total += len(changed)
            changed, tick = set(), e.arrival // trigger
        dropped = agg.dropped
        agg.process(e)
        if agg.dropped == dropped:
            changed.add((tumbling_start(e.event_time, size), e.category))
    return total + len(changed)


def peak_state_with_keys(events, lateness, n_keys):
    """集計のキーを n_keys 種類に増やしたときの、状態の最大件数 (カテゴリ 5 種類を顧客などに置き換えた想定)。"""
    rekeyed = [replace(e, category=f"k{e.event_id % n_keys}") for e in events]
    return evaluate(rekeyed, lateness)["peak_state"]
