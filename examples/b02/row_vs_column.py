"""行指向と列指向の違いを、Python の list と dict で再現します。"""

# 行指向: 1 件ずつ、すべての項目をまとめて持つ（注文明細を 1 行ずつ）
rows = [
    {"order_id": 1, "category": "寝具", "unit_price": 3200, "quantity": 1},
    {"order_id": 2, "category": "寝具", "unit_price": 1800, "quantity": 2},
    {"order_id": 3, "category": "飲み物", "unit_price": 900, "quantity": 3},
    {"order_id": 4, "category": "飲み物", "unit_price": 650, "quantity": 1},
    {"order_id": 5, "category": "飲み物", "unit_price": 700, "quantity": 2},
]


def to_columns(rows: list[dict]) -> dict[str, list]:
    """行の並びを、項目ごとの並びに組み替えます。"""
    return {key: [row[key] for row in rows] for key in rows[0]}


def run_length_encode(values: list) -> list[tuple]:
    """同じ値が続く部分を (値, 続く回数) にまとめます。列指向の圧縮の考え方の一例です。"""
    encoded: list[tuple] = []
    for v in values:
        if encoded and encoded[-1][0] == v:
            encoded[-1] = (v, encoded[-1][1] + 1)
        else:
            encoded.append((v, 1))
    return encoded


columns = to_columns(rows)
# 行指向で unit_price の合計を出すには、全行をたどって 1 項目ずつ取り出す
total_from_rows = sum(row["unit_price"] for row in rows)
# 列指向なら unit_price の並びだけを読めばよい
total_from_columns = sum(columns["unit_price"])

if __name__ == "__main__":
    print(columns)
    print(total_from_rows, total_from_columns)
    print(run_length_encode(columns["category"]))
