import json

data = json.load("orders.json")
print(data["orders"][0]["order_id"])
