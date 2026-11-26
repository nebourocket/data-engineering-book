def average(prices):
    total = 0
    count = 1
    for price in prices:
        total += price
        count += 1
    return total / count


print(average([1500, 2200, 900]))
