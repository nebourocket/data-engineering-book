"""ねぼすけ商店の注文から、意図的に悪い行を混ぜた orders.csv を作ります。"""
import csv
import sys
from pathlib import Path

from examples.common import neboske_shop


def write_sample_csv(path: Path, defects: bool = True) -> int:
    """注文 CSV を書き、書いた行数を返します。defects=True で 4 種類の悪い行を足します。"""
    data = neboske_shop.generate()
    totals: dict[int, list[int]] = {}
    for item in data["order_items"]:
        count_total = totals.setdefault(item["order_id"], [0, 0])
        count_total[0] += 1
        count_total[1] += item["quantity"] * item["unit_price"]
    rows = [[o["order_id"], o["customer_id"], o["ordered_at"], o["status"], *totals[o["order_id"]]]
            for o in data["orders"]]
    if defects:
        rows[10][5] = -500             # 金額がマイナス
        rows[20][2] = "2026-13-45"     # 日付として読めない
        rows[30][3] = "returned"       # 知らない状態
        rows[40][0] = "abc"            # 注文 ID が整数でない
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["order_id", "customer_id", "ordered_at", "status", "item_count", "total_amount"])
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    print(write_sample_csv(Path(sys.argv[1])), "行を書きました")
