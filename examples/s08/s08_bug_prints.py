def total_price(prices):
    total = 0
    for price in prices:
        total = price
        print("price =", price, "total =", total)
    return total


print(total_price([1500, 2200, 900]))
