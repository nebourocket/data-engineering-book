import csv

with open("orders.csv", encoding="utf-8", newline="") as f:
    orders = list(csv.DictReader(f))
print(len(orders))
print(orders[0])
