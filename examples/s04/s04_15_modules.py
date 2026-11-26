import math
from datetime import date
from pathlib import Path

print(math.sqrt(16))
print(math.ceil(2.1))
print(math.floor(2.9))

d = date(2026, 11, 14)
print(d)
print(d.year, d.month, d.day)
print((date(2026, 12, 25) - d).days)

p = Path("data") / "orders.csv"
print(p)
print(p.name, p.suffix)
print(Path("orders.csv").exists())
