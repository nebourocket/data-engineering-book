import csv

with open("orders.csv", encoding="utf-8", newline="") as f:
    orders = list(csv.DictReader(f))

sales = {}
for order in orders:
    amount = int(order["price"]) * int(order["quantity"])
    sales[order["item"]] = sales.get(order["item"], 0) + amount
print(sales)
