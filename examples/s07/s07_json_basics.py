"""JSON の文字列と、Python の辞書・リストの対応を確かめます。"""
import json

text = '{"order_id": 1001, "paid": true, "coupon": null, "items": ["アイマスク", "置き時計"]}'

order = json.loads(text)
print(order)
print(type(order).__name__, type(order["order_id"]).__name__, type(order["paid"]).__name__,
      type(order["coupon"]).__name__, type(order["items"]).__name__)
print(order["items"][0])

# Python の値を JSON の文字列にする。日本語をそのまま出すには ensure_ascii=False
print(json.dumps(order))
print(json.dumps(order, ensure_ascii=False, indent=2))
