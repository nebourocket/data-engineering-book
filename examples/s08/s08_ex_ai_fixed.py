import json

with open("examples/s07/s07_shop_orders.json", encoding="utf-8") as f:
    data = json.load(f)
print(data["orders"][0]["order_id"])
