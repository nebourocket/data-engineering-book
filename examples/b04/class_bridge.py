from dataclasses import dataclass


def shout(func):
    """関数を包んで、結果を大文字にして返す関数に作り替えます (デコレーターの例)。"""
    def wrapper(name):
        return func(name).upper()
    return wrapper


@shout
def greet(name):
    return "hello, " + name


@dataclass(frozen=True)
class Point:
    x: int
    y: int


p = Point(1, 2)
print(greet("neboske"))
print(p)
print(p.x + p.y)
try:
    p.x = 10
except AttributeError as e:
    print(type(e).__name__)
