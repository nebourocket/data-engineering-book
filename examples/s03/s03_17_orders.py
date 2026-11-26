orders = [
    {"order_id": 1, "item": "アイマスク", "price": 1500, "quantity": 2},
    {"order_id": 2, "item": "マグカップ", "price": 480, "quantity": 4},
    {"order_id": 3, "item": "コーヒー豆", "price": 1200, "quantity": 1},
    {"order_id": 4, "item": "枕", "price": 4800, "quantity": 1},
    {"order_id": 5, "item": "アイマスク", "price": 1500, "quantity": 3},
]

print(len(orders))
print(orders[0]["item"])

total = 0
for order in orders:
    total = total + order["price"] * order["quantity"]
print(f"合計: {total}円")

big = 0
for order in orders:
    if order["price"] * order["quantity"] >= 3000:
        big = big + 1
print(f"3000円以上の注文: {big}件")

top = orders[0]
for order in orders:
    if order["price"] > top["price"]:
        top = order
print(f"一番高い商品: {top['item']} ({top['price']}円)")
