import tempfile
from pathlib import Path

from neboske_etl.reader import iter_rows

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "orders.csv"
    path.write_text(
        "order_id,customer_id,ordered_at,status,item_count,total_amount\n"
        "1,10,2026-01-01 09:00:00,placed,1,1200\n"
        "2,11,2026-01-01 09:05:00,shipped,2,3400\n"
        "3,12,2026-01-01 09:10:00,delivered,1,800\n",
        encoding="utf-8",
    )
    rows = iter_rows(path)
    print(type(rows).__name__)
    print(next(rows)["order_id"])
    print(next(rows)["order_id"])
    print([row["order_id"] for row in rows])
