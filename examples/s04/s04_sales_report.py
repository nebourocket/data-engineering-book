import csv
import sys


def read_orders(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def total_by_item(orders):
    sales = {}
    skipped = 0
    for order in orders:
        try:
            amount = int(order["price"]) * int(order["quantity"])
        except ValueError:
            print(f"飛ばした注文: {order['order_id']}番 {order}")
            skipped = skipped + 1
            continue
        sales[order["item"]] = sales.get(order["item"], 0) + amount
    return sales, skipped


def write_sales(path, sales):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["item", "sales"])
        writer.writeheader()
        for item, amount in sales.items():
            writer.writerow({"item": item, "sales": amount})


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "orders.csv"
    orders = read_orders(path)
    sales, skipped = total_by_item(orders)
    write_sales("sales.csv", sales)
    print(f"{len(orders)}件の注文から{len(sales)}商品の売上を書き出しました (飛ばした注文 {skipped}件)")


if __name__ == "__main__":
    main()
