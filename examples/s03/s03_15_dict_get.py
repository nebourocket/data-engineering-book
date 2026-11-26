order = {"order_id": 1, "item": "アイマスク", "price": 1500}
print(order.get("quantity"))
print(order.get("quantity", 1))
for key, value in order.items():
    print(f"{key} -> {value}")
for key in order:
    print(key)
