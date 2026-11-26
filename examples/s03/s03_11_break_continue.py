prices = [1500, 0, 480, 4800, 1200]
for price in prices:
    if price == 0:
        print("0円は飛ばします")
        continue
    if price > 4000:
        print(f"{price}円は高すぎるので、ここで止めます")
        break
    print(f"{price}円を処理しました")
