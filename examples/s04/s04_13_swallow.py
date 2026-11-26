prices = ["1500", "480", "せんえん", "1200"]
total = 0
for p in prices:
    try:
        total = total + int(p)
    except:
        pass
print(total)
