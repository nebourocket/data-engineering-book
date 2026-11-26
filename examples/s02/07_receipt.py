# ねぼすけ商店のレシートを作ります。
name = input("商品名: ")
price = int(input("値段(円): "))
quantity = int(input("個数: "))

subtotal = price * quantity
tax = subtotal * 10 // 100
shipping = 500
total = subtotal + tax + shipping

print("--- ねぼすけ商店 レシート ---")
print(f"{name} {price}円 x {quantity}個 = {subtotal}円")
print(f"消費税(10%): {tax}円")
print(f"送料: {shipping}円")
print(f"合計: {total}円")
