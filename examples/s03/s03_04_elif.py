quantity = 12
if quantity >= 20:
    rate = 20
elif quantity >= 10:
    rate = 10
elif quantity >= 5:
    rate = 5
else:
    rate = 0
print(f"{quantity}個の割引: {rate}%")
