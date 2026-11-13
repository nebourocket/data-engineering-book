"""第 12 章: 日次ジョブの入力になる売上明細 CSV（1 行 = 1 明細）を、ねぼすけ商店のデータから作ります。

使い方: python examples/b12/make_source.py
work/source/sales.csv ができます。列は order_id, ordered_at, status, category, quantity, unit_price です。
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import generate  # noqa: E402

COLUMNS = ["order_id", "ordered_at", "status", "category", "quantity", "unit_price"]


def write_sales(path: Path, seed: int = 42) -> int:
    """売上明細を path に書き、行数を返します。"""
    data = generate(seed)
    category = {p["product_id"]: p["category"] for p in data["products"]}
    orders = {o["order_id"]: o for o in data["orders"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for item in data["order_items"]:
            o = orders[item["order_id"]]
            writer.writerow([o["order_id"], o["ordered_at"], o["status"], category[item["product_id"]],
                             item["quantity"], item["unit_price"]])
    return len(data["order_items"])


if __name__ == "__main__":
    print(f"{write_sales(Path('work/source/sales.csv'))} 行を work/source/sales.csv に書きました")
