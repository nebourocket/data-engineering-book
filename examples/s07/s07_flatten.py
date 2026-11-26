"""入れ子の JSON を、1 行に 1 つの商品の表 (辞書のリスト) に直します。"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def flatten(data):
    """注文の中の商品を 1 つずつ取り出し、注文と顧客の情報を同じ行に並べます。"""
    rows = []
    for order in data["orders"]:
        for item in order["items"]:
            rows.append({
                "order_id": order["order_id"],
                "customer": order["customer"]["name"],
                "prefecture": order["customer"]["prefecture"],
                "coupon": order["coupon"],
                "product": item["product"],
                "price": item["price"],
                "quantity": item["quantity"],
            })
    return rows


if __name__ == "__main__":
    data = json.loads((HERE / "s07_shop_orders.json").read_text(encoding="utf-8"))
    print(len(data["orders"]), "件の注文")
    rows = flatten(data)
    print(len(rows), "行の表")
    print(rows[0])
