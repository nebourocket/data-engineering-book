values = ["3", "x", "5"]
total = 0
for v in values:
    try:
        total = total + int(v)
    except ValueError:
        print(f"{v!r} は数ではないので飛ばします")
print(total)
