"""第 11 章: 本文の「小さな数字の例」の表を、コードで計算して data/tables/ の CSV に書きます。

使い方: python examples/b11/tiny_tables.py
手で数字を写さないために、表の中身はすべてここで計算します。テストは、書き出した CSV が最新かを確かめます。
"""
import csv
import math
from pathlib import Path

TABLES = Path(__file__).resolve().parents[2] / "data" / "tables"
VALUES = [7, 91, 42, 15, 88, 23, 60, 5]  # 顧客番号が 8 行ぶん
GROUP = 2  # 行グループの大きさ（本物は 10,000 行など）
TARGET = 42


def zonemap_rows() -> list[list]:
    """同じ 8 行を「ばらばら」と「並べ替え済み」で 2 行ずつに分け、42 を探すとき読む行グループを調べる。"""
    rows = []
    for label, values in [("ばらばら", VALUES), ("並べ替え済み", sorted(VALUES))]:
        for i in range(0, len(values), GROUP):
            part = values[i:i + GROUP]
            read = min(part) <= TARGET <= max(part)
            rows.append([label, i // GROUP + 1, " と ".join(map(str, part)), min(part), max(part),
                         "読む" if read else "読み飛ばす"])
    return rows


def vector_rows() -> list[list]:
    """行数と塊の大きさから、関数を呼ぶ回数を数える（1 行ずつなら行数と同じ）。"""
    return [[n, size, n, math.ceil(n / size)] for n, size in [(8, 4), (150_168, 2048)]]


def partial_rows() -> list[list]:
    """売上が [100] の月と [200, 200, 200] の月から、全体の平均を 2 通りに求める。"""
    months = {"A 月": [100], "B 月": [200, 200, 200]}
    rows = [[m, " と ".join(map(str, v)), sum(v), len(v), sum(v) / len(v)] for m, v in months.items()]
    total, n = sum(r[2] for r in rows), sum(r[3] for r in rows)
    rows.append(["正しい全体（合計の合計 ÷ 件数の合計）", "", total, n, total / n])
    rows.append(["平均の平均（月ごとの平均を平均）", "", "", "", sum(r[4] for r in rows[:2]) / 2])
    return rows


def tables() -> dict[str, tuple[list[str], list[list]]]:
    return {
        "b11-zonemap-tiny": (["並べ方", "行グループ", "入っている値", "最小", "最大", f"{TARGET} を探すとき"], zonemap_rows()),
        "b11-vector-tiny": (["行数", "塊の大きさ", "1 行ずつの呼び出し回数", "塊ごとの呼び出し回数"], vector_rows()),
        "b11-partial-tiny": (["月", "売上", "合計", "件数", "平均"], partial_rows()),
    }


if __name__ == "__main__":
    for name, (header, rows) in tables().items():
        with (TABLES / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        print(f"{name}.csv を書きました（{len(rows)} 行）")
