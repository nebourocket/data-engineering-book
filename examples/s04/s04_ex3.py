import csv

count = 0
with open("orders.csv", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        if int(row["quantity"]) >= 3:
            count = count + 1
print(count)
