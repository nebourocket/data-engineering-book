try:
    with open("nothing.txt", encoding="utf-8") as f:
        text = f.read()
except FileNotFoundError:
    print("nothing.txt が見つかりません。フォルダを確かめてください")
    text = ""
finally:
    print("読み込みの処理を終わります")
