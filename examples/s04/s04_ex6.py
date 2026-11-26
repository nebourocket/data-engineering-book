import csv

rows = [
    {"item": "枕", "stock": 10},
    {"item": "毛布", "stock": 4},
]
with open("stock.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["item", "stock"])
    writer.writeheader()
    writer.writerows(rows)

with open("stock.csv", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        print(row["item"], int(row["stock"]) * 2)
