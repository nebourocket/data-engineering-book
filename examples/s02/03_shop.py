# 商品の値段と個数から、合計を計算します。
price = 1200
quantity = 3
subtotal = price * quantity
print(subtotal)

tax = subtotal * 10 // 100
shipping = 500
total = subtotal + tax + shipping
print(tax)
print(total)

quantity = quantity + 1
print(quantity)
print(price * quantity)
