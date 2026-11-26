"""第12章: 作る・買う・OSS を使う、の 3 年間の総費用 (TCO)。作り話の数字 (仮定) で、人の時間まで入れて比べます。"""
HOUR_YEN = 5000       # 1 時間あたりの人件費 (仮定)
OPPORTUNITY = 1.5     # 機会費用の係数。この時間で本来できた仕事の価値を、人件費の 1.5 倍と見る (仮定)
MONTHS = 36

# 初期の作業時間, 毎月の運用時間, 毎月の現金 (ライセンス料・サーバー代) (円)
OPTIONS = {
    "build": {"setup_hours": 300, "monthly_hours": 12, "monthly_cash": 10_000},
    "oss": {"setup_hours": 100, "monthly_hours": 20, "monthly_cash": 12_000},
    "buy": {"setup_hours": 40, "monthly_hours": 6, "monthly_cash": 150_000},
}


def cumulative_cost(option, month, monthly_hours=None):
    """month か月目までの累計費用 (円)。人の時間は HOUR_YEN x OPPORTUNITY で円に直します。"""
    o = OPTIONS[option]
    hours = o["monthly_hours"] if monthly_hours is None else monthly_hours
    people = HOUR_YEN * OPPORTUNITY
    return o["setup_hours"] * people + month * (hours * people + o["monthly_cash"])


def break_even_month(a, b):
    """a の累計が b 以下になる最初の月。MONTHS か月以内に無ければ None。"""
    for m in range(1, MONTHS + 1):
        if cumulative_cost(a, m) <= cumulative_cost(b, m):
            return m
    return None


def cheapest(month):
    return min(OPTIONS, key=lambda name: cumulative_cost(name, month))


def max_build_hours():
    """作る案の毎月の運用時間が何時間までなら、MONTHS か月目に作る案が最安のままか。"""
    h = 0
    while all(cumulative_cost("build", MONTHS, h + 1) <= cumulative_cost(o, MONTHS) for o in ("oss", "buy")):
        h += 1
    return h
