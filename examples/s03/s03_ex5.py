orders = [
    {"item": "アイマスク", "quantity": 2},
    {"item": "マグカップ", "quantity": 4},
    {"item": "アイマスク", "quantity": 3},
]
count = 0
for order in orders:
    if order["item"] == "アイマスク":
        count = count + order["quantity"]
print(count)
