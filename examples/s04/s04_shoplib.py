def add_tax(price):
    return price * 110 // 100


def calc_total(price, quantity=1, shipping=500):
    return price * quantity + shipping


if __name__ == "__main__":
    print(add_tax(1000))
