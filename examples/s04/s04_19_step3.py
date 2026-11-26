import csv


def read_orders(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def total_by_item(orders):
    sales = {}
    for order in orders:
        amount = int(order["price"]) * int(order["quantity"])
        sales[order["item"]] = sales.get(order["item"], 0) + amount
    return sales


def write_sales(path, sales):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["item", "sales"])
        writer.writeheader()
        for item, amount in sales.items():
            writer.writerow({"item": item, "sales": amount})


def main():
    orders = read_orders("orders.csv")
    sales = total_by_item(orders)
    write_sales("sales.csv", sales)
    print(f"{len(orders)}件の注文から{len(sales)}商品の売上を書き出しました")


if __name__ == "__main__":
    main()
