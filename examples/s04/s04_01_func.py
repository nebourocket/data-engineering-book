def add_tax(price):
    return price * 110 // 100


print(add_tax(1000))
total = add_tax(1500) + add_tax(480)
print(total)
