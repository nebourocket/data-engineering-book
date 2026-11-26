"""カンマ・引用符・改行を含む欄は、CSV では引用符で囲まれます。"""
import csv
import io

rows = [
    ["order_id", "product", "note"],
    [1001, "アイマスク", "ギフト用, のし付き"],
    [1002, "置き時計", '「"静か"な音」希望'],
    [1003, "コーヒー豆", "1行目\n2行目"],
]

buffer = io.StringIO(newline="")
csv.writer(buffer, lineterminator="\n").writerows(rows)
text = buffer.getvalue()
print(text)

# 行ごとに分けてから、カンマで割る方法 (間違い)
for line in text.splitlines():
    print(len(line.split(",")), line.split(","))

# csv モジュールで読む (正しい)
for record in csv.reader(io.StringIO(text, newline="")):
    print(len(record), record)
