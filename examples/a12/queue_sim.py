"""第12章: 依頼を 1 つのチームが受ける窓口の待ち行列。作り話の数字 (仮定) で、チーム数と待ち日数の関係を見ます。"""
import math
import random
import statistics

DAYS_PER_WEEK = 5
CAPACITY_HOURS = 60       # 窓口チームが 1 週間に依頼へ使える時間 (2 人 x 30 時間)
MEAN_HOURS = 4            # 依頼 1 件の平均の作業時間
REQUESTS_PER_TEAM = 2     # 1 チームが 1 週間に出す依頼の数 (平均)
BUILD_HOURS = 180         # 舗装された道を作るのにかかる時間 (6 人週 x 30 時間、仮定)


def rates(n_teams, self_serve_share):
    """(1 週間あたりの到着数 lam, 1 週間あたりに処理できる数 mu)。窓口に届くのは、自分で済まなかった分です。"""
    return n_teams * REQUESTS_PER_TEAM * (1 - self_serve_share), CAPACITY_HOURS / MEAN_HOURS


def analytic_wait_days(lam, mu):
    """M/M/1 の待ち時間の平均 (日)。lam >= mu なら定常状態がなく None。"""
    if lam >= mu:
        return None
    return lam / (mu * (mu - lam)) * DAYS_PER_WEEK


def pk_wait_days(lam, mu, cv):
    """処理時間のばらつき (変動係数 cv = 標準偏差 / 平均) を入れた M/G/1 の平均の待ち (日)。
    cv = 1 (指数分布) で M/M/1 と一致します。ばらつきが大きいほど、待ちは (1 + cv^2) / 2 倍に伸びます。"""
    if lam >= mu:
        return None
    return (1 + cv ** 2) / 2 * lam / (mu * (mu - lam)) * DAYS_PER_WEEK


def service_time(rng, mu, cv):
    """平均 1/mu、変動係数 cv の処理時間。cv = 1 は指数分布、それ以外は対数正規分布です。"""
    if cv == 1.0:
        return rng.expovariate(mu)
    sigma2 = math.log(1 + cv ** 2)
    return rng.lognormvariate(math.log(1 / mu) - sigma2 / 2, math.sqrt(sigma2))


def simulate(lam, mu, weeks, seed, cv=1.0):
    """到着間隔は指数分布、処理時間は service_time で作り、先着順に 1 件ずつ待ち時間 (日) を返します (Lindley の漸化式)。"""
    rng = random.Random(seed)
    t, free_at, waits = 0.0, 0.0, []
    while True:
        t += rng.expovariate(lam)
        if t > weeks:
            return waits
        start = max(t, free_at)
        waits.append((start - t) * DAYS_PER_WEEK)
        free_at = start + service_time(rng, mu, cv)


def summarize(lam, mu, weeks=52, runs=200, cv=1.0):
    """runs 回 (種 0..runs-1) 回した、平均の待ち日数と 90 パーセンタイルの平均。"""
    means, p90s = [], []
    for seed in range(runs):
        waits = sorted(simulate(lam, mu, weeks, seed, cv))
        means.append(statistics.fmean(waits))
        p90s.append(waits[int(0.9 * (len(waits) - 1))])
    return statistics.fmean(means), statistics.fmean(p90s)


def min_self_serve_share(n_teams, target_rho=0.8):
    """窓口の稼働率を target_rho 以下にするために、自分で済ませる必要がある割合の下限。"""
    lam_all, mu = rates(n_teams, 0)
    return max(0.0, 1 - target_rho * mu / lam_all)


def payback_weeks(n_teams, share):
    """舗装された道に BUILD_HOURS かけて、依頼の share が窓口を通らなくなるとき、作業時間が元を取るまでの週数 (小数第 1 位で切り上げ)。"""
    lam_all, _ = rates(n_teams, 0)
    saved_per_week = lam_all * share * MEAN_HOURS
    return math.ceil(BUILD_HOURS / saved_per_week * 10) / 10  # 週数は小数第 1 位で切り上げ
