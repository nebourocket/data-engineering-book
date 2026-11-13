import csv

total = 0
shipped = 0
for row in csv.DictReader(open("orders.csv")):
    print(row["order_id"])
    order_id = int(row["order_id"])
    total += int(row["total_amount"])
    if row["status"] == "shipped":
        shipped += 1
print(total, shipped)
