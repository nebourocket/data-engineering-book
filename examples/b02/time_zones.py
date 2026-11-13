"""日時とタイムゾーンの実験です。ねぼすけ商店の日時は日本時間（JST）の文字列とみなします。"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.common.neboske_shop import generate  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
FORMAT = "%Y-%m-%d %H:%M:%S"


def daily_counts(orders: list[dict], tz) -> Counter:
    """注文を tz の暦の日付ごとに数えます。ordered_at は JST の時刻として読みます。"""
    counts: Counter = Counter()
    for o in orders:
        jst_time = datetime.strptime(o["ordered_at"], FORMAT).replace(tzinfo=JST)
        counts[jst_time.astimezone(tz).date().isoformat()] += 1
    return counts


# 同じ時刻を、UTC では前日になる例
moment = datetime(2026, 3, 1, 8, 30, tzinfo=JST)
print(moment.isoformat(), "->", moment.astimezone(UTC).isoformat())

# 夏時間のある地域では、「1 日」が 24 時間とは限らない
NY = ZoneInfo("America/New_York")
start = datetime(2026, 3, 8, 0, 0, tzinfo=NY)
end = datetime(2026, 3, 9, 0, 0, tzinfo=NY)
print(end - start)  # 同じタイムゾーンの引き算は、壁の時計の差になる
print(end.astimezone(UTC) - start.astimezone(UTC))  # UTC にそろえると実際の経過時間

# 同じ注文でも、日付の区切りを JST にするか UTC にするかで日ごとの件数が変わる
orders = generate()["orders"]
jst_counts = daily_counts(orders, JST)
utc_counts = daily_counts(orders, UTC)
differing = [d for d in sorted(jst_counts) if jst_counts[d] != utc_counts.get(d, 0)]
print(len(jst_counts), "日のうち件数が食い違う日:", len(differing))
day = max(differing, key=lambda d: jst_counts[d])  # 件数がいちばん多い日で見る
print(day, "JST:", jst_counts[day], "UTC:", utc_counts[day])
