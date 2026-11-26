with open("memo.txt", "a", encoding="utf-8") as f:
    f.write("コーヒー豆 1200\n")

with open("memo.txt", encoding="utf-8") as f:
    lines = f.readlines()
print(len(lines))
print(lines[-1].strip())
