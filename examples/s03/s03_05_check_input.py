text = input("個数: ")
if text.isascii() and text.isdigit():
    quantity = int(text)
    print(f"{quantity}個で{1200 * quantity}円です")
else:
    print(f"「{text}」は数ではありません。半角の数字で入れてください")
