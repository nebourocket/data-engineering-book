"""横持ちの表を縦持ちに直します。"""
# 横持ち: 月が列になっている (1 行に 1 つの商品)
wide = [
    {"product": "アイマスク", "jan": 12, "feb": 9, "mar": 15},
    {"product": "置き時計", "jan": 4, "feb": 6, "mar": 5},
]


def to_long(rows):
    """月の列を、「月」と「個数」の 2 つの列に分けて、1 行に 1 つの (商品, 月) にします。"""
    long_rows = []
    for row in rows:
        for month in ("jan", "feb", "mar"):
            long_rows.append({"product": row["product"], "month": month, "quantity": row[month]})
    return long_rows


long_rows = to_long(wide)
for row in long_rows:
    print(row)
print(len(wide), "行 ->", len(long_rows), "行")
