"""第 7 章の練習問題の解答例です。"""
import csv
import io
import json
from pathlib import Path

from s07_flatten import flatten

HERE = Path(__file__).resolve().parent


def answer1(long_rows):
    """問 1: 縦持ちの行から、月ごとの合計個数を辞書にします。"""
    totals = {}
    for row in long_rows:
        totals[row["month"]] = totals.get(row["month"], 0) + row["quantity"]
    return totals


def answer2():
    """問 2: 「ギフト用, のし付き」を含む行を csv モジュールで書くと、どう見えるか。"""
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerow([1001, "アイマスク", "ギフト用, のし付き"])
    return buffer.getvalue()


def answer3():
    """問 3: 入れ子の JSON から、顧客の都道府県を取り出す。"""
    text = '{"order_id": 1002, "customer": {"name": "鈴木 花子", "prefecture": "大阪"}}'
    order = json.loads(text)
    return order["customer"]["prefecture"]


def answer4():
    """問 4: クーポンを使った注文の番号を、重複なしで集める。"""
    data = json.loads((HERE / "s07_shop_orders.json").read_text(encoding="utf-8"))
    used = set()
    for row in flatten(data):
        if row["coupon"] is not None:
            used.add(row["order_id"])
    return sorted(used)
