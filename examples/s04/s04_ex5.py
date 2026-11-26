from datetime import date
from pathlib import Path

today = date(2026, 11, 14)
print((date(2026, 12, 31) - today).days)
print(Path("data/sales.csv").suffix)
