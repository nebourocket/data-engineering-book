def tax_included(price, rate=10):
    return price * (100 + rate) // 100


print(tax_included(1000))
print(tax_included(1000, 8))
print(tax_included(price=500, rate=8))
