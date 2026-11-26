import csv

products = [
    {"item": "アイマスク", "price": 1500},
    {"item": "マグカップ", "price": 480},
]
with open("products.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["item", "price"])
    writer.writeheader()
    for product in products:
        writer.writerow(product)

with open("products.csv", encoding="utf-8") as f:
    print(f.read())
