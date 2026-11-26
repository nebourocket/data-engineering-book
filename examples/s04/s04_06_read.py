with open("memo.txt", encoding="utf-8") as f:
    text = f.read()
print(repr(text))
print(len(text))

with open("memo.txt", encoding="utf-8") as f:
    for line in f:
        print(line.rstrip("\n"))
