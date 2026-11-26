"""「売上ダッシュボードを作って」の最小版: ねぼすけ商店の日別売上を集計します。"""
import sys
import tempfile
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.common.neboske_shop import write_duckdb  # noqa: E402

# 「売上」の定義がひとつ決まる: キャンセル以外の注文の、数量 x 単価の合計。
# （未発送の placed を含めるかどうかも本当は確かめる。ここでは含める。）
DAILY_SALES_SQL = """
SELECT substr(o.ordered_at, 1, 10) AS day,
       count(DISTINCT o.order_id) AS orders,
       sum(i.quantity * i.unit_price) AS sales
FROM orders AS o
JOIN order_items AS i USING (order_id)
WHERE o.status <> 'cancelled'
GROUP BY day
ORDER BY day
"""

# status に "SHIPPED" と "shipped" が混ざっている。そろえずに数えると漏れる。
SHIPPED_COUNT_SQL = """
SELECT count(*) FILTER (WHERE status = 'shipped') AS exact,
       count(*) FILTER (WHERE lower(status) = 'shipped') AS lowered
FROM orders
"""

ALL_SALES_SQL = "SELECT sum(quantity * unit_price) FROM order_items"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "shop.duckdb"
        write_duckdb(path)
        con = duckdb.connect(str(path), read_only=True)
        print(con.execute("SELECT status, count(*) FROM orders GROUP BY status ORDER BY status").fetchall())
        print(con.execute(SHIPPED_COUNT_SQL).fetchone())
        for row in con.execute(DAILY_SALES_SQL).fetchall()[:3]:
            print(row)
        counted = con.execute(f"SELECT sum(sales) FROM ({DAILY_SALES_SQL})").fetchone()[0]
        everything = con.execute(ALL_SALES_SQL).fetchone()[0]
        print(f"キャンセルを除いた売上 {counted:,} 円 / 明細すべての合計 {everything:,} 円")
        con.close()


if __name__ == "__main__":
    main()
