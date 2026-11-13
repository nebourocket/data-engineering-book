"""第 12 章: 日次ジョブの入力になる売上明細 CSV を、日付ごとのフォルダに作ります（1 行 = 1 明細）。

使い方: python examples/b12/make_source.py
work/source/date=2026-03-05/sales.csv のように 1 日 1 フォルダで、書き終えたら最後に _SUCCESS を置きます。
注文が無い日も、見出しだけの sales.csv と _SUCCESS を置きます（「届いたが 0 件」と「まだ届かない」を区別するため）。
日付は、ねぼすけ商店の ordered_at の日付部分（日本時間の日付として扱います）です。
"""
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import generate  # noqa: E402

COLUMNS = ["order_id", "ordered_at", "status", "category", "quantity", "unit_price"]
FIRST_DAY = date(2026, 1, 1)
LAST_DAY = date(2026, 7, 31)


def write_sales(root: Path, seed: int = 42) -> int:
    """root の下に日付ごとのフォルダを作り、明細の行数を返します。_SUCCESS は各日の最後に置きます。"""
    data = generate(seed)
    category = {p["product_id"]: p["category"] for p in data["products"]}
    orders = {o["order_id"]: o for o in data["orders"]}
    by_day: dict[str, list[list]] = {}
    for item in data["order_items"]:
        o = orders[item["order_id"]]
        by_day.setdefault(o["ordered_at"][:10], []).append(
            [o["order_id"], o["ordered_at"], o["status"], category[item["product_id"]],
             item["quantity"], item["unit_price"]])
    day = FIRST_DAY
    while day <= LAST_DAY:
        folder = root / f"date={day.isoformat()}"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "sales.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            writer.writerows(by_day.get(day.isoformat(), []))
        (folder / "_SUCCESS").touch()
        day += timedelta(days=1)
    return len(data["order_items"])


if __name__ == "__main__":
    print(f"{write_sales(Path('work/source'))} 行を work/source/ に書きました")
