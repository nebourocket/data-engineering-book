with open("shopping.txt", "w", encoding="utf-8") as f:
    f.write("アイマスク\n")
    f.write("マグカップ\n")
    f.write("コーヒー豆\n")

number = 1
with open("shopping.txt", encoding="utf-8") as f:
    for line in f:
        print(f"{number}. {line.rstrip()}")
        number = number + 1
