def find_price(menu, name):
    return menu[name]


def make_receipt(menu, name, quantity):
    price = find_price(menu, name)
    return price * quantity


menu = {"アイマスク": 1500, "置き時計": 2200}
print(make_receipt(menu, "アイマスク", 2))
print(make_receipt(menu, "マグカップ", 1))
