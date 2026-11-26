text = "3個"
try:
    quantity = int(text)
except ValueError:
    print(f"「{text}」は整数にできません")
    quantity = 0
print(quantity)
