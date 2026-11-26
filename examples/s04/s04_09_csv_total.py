import csv

total = 0
with open("orders.csv", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        total = total + int(row["price"]) * int(row["quantity"])
print(f"売上の合計: {total}円")
