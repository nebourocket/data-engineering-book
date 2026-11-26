prices = ["1500", "480", "せんえん", "1200"]
total = 0
skipped = 0
for p in prices:
    try:
        total = total + int(p)
    except ValueError:
        print(f"数にできない値を飛ばしました: {p!r}")
        skipped = skipped + 1
print(f"合計 {total}円 (飛ばした件数 {skipped})")
