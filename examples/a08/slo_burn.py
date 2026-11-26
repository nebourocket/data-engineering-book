"""第8章: 鮮度の SLO とエラーバジェット、バーンレート (予算を使う速さ) によるアラートを、30 日ぶんの生成データで動かします。"""
import contract_check

STEP = 5               # SLI を測る間隔 (分)
DAYS = 30
SLO = 0.95             # 30 日のうち 95% の時間、データの遅れが LIMIT 分以内
LIMIT = contract_check.load_contract()["sla"]["freshness_minutes"]  # 遅れの上限 (分)。第 7 章の契約の書類から読む
WINDOWS = {"5m": 1, "30m": 6, "1h": 12, "6h": 72, "3d": 864}  # 窓の長さ (測定回数)
# 止まった読み込み: (開始の分, 止まっていた分)。1 日 = 1440 分
BIG = [(12 * 1440 + 600, 300), (20 * 1440 + 120, 150)]
FLAPPING = [((3 * i + 2) * 1440 + 480, 55) for i in range(6)]  # 55 分の短い停止が 6 回


def build_lag(stalls):
    """30 分ごとに読み込みが成功するパイプラインの「データの遅れ (分)」を STEP 分ごとに返す。stalls の間は読み込みが失敗する。"""
    lag, last_ok = [], 0
    for t in range(0, DAYS * 1440, STEP):
        if t % 30 == 0 and not any(s <= t < s + n for s, n in stalls):
            last_ok = t
        lag.append(t - last_ok + 10)  # 10 分は読み込み自体にかかる時間
    return lag


def bad_flags(lag):
    return [1 if x > LIMIT else 0 for x in lag]


def burn_rates(bad, window):
    """各時点で終わる窓の、悪い割合 / (1 - SLO)。1 なら予算を使い切るちょうどの速さ。窓が足りない始めの部分は 0 とする。"""
    prefix = [0]
    for b in bad:
        prefix.append(prefix[-1] + b)
    return [0.0 if i + 1 < window else (prefix[i + 1] - prefix[i + 1 - window]) / window / (1 - SLO)
            for i in range(len(bad))]


def firings(flags):
    """False から True に変わった時点の番号 (アラートが鳴り始めた時点)。"""
    return [i for i in range(len(flags)) if flags[i] and (i == 0 or not flags[i - 1])]


def alert_rules(bad):
    """SRE ワークブックの 3 組: 1 時間 14.4 倍 (ページ)・6 時間 6 倍 (ページ)・3 日 1 倍 (チケット)。それぞれ短い窓も同時に超えたときだけ鳴る。"""
    r = {name: burn_rates(bad, n) for name, n in WINDOWS.items()}
    n = len(bad)
    return {
        "page_fast": [r["1h"][i] >= 14.4 and r["5m"][i] >= 14.4 for i in range(n)],
        "page_slow": [r["6h"][i] >= 6 and r["30m"][i] >= 6 for i in range(n)],
        "ticket": [r["3d"][i] >= 1 and r["6h"][i] >= 1 for i in range(n)],
        "naive": [b == 1 for b in bad],
    }


def budget_used(bad):
    """30 日の予算 (悪くてよい測定回数) のうち、使った割合。"""
    return sum(bad) / (len(bad) * (1 - SLO))
