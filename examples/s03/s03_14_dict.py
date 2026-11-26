order = {"order_id": 1, "item": "アイマスク", "price": 1500, "quantity": 2}
print(order)
print(order["item"])
print(order["price"] * order["quantity"])
order["quantity"] = 3
order["status"] = "shipped"
print(order)
print(len(order))
print("item" in order)
