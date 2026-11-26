import json

text = '{"order_id": 1001, "items": ["アイマスク", "置き時計",]}'
print(json.loads(text))
