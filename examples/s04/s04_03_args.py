def calc_total(price, quantity=1, shipping=500):
    return price * quantity + shipping


print(calc_total(1500))
print(calc_total(1500, 2))
print(calc_total(1500, 2, 0))
print(calc_total(1500, shipping=0))
print(calc_total(price=480, quantity=4))
