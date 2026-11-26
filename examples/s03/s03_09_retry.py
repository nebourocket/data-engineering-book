text = input("個数: ")
while not (text.isascii() and text.isdigit()):
    text = input("半角の数字で入れてください。個数: ")
print(f"{int(text)}個ですね")
