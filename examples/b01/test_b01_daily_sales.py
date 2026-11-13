import duckdb

import daily_sales
from examples.common.neboske_shop import write_duckdb


def test_cancelled_orders_are_excluded(tmp_path):
    write_duckdb(tmp_path / "shop.duckdb")
    con = duckdb.connect(str(tmp_path / "shop.duckdb"), read_only=True)
    statuses = {s for (s,) in con.execute("SELECT DISTINCT status FROM orders").fetchall()}
    assert {"shipped", "SHIPPED"} <= statuses  # 表記ゆれが入っている
    counted = con.execute(f"SELECT sum(sales) FROM ({daily_sales.DAILY_SALES_SQL})").fetchone()[0]
    everything = con.execute(daily_sales.ALL_SALES_SQL).fetchone()[0]
    assert 0 < counted < everything
    days = con.execute(daily_sales.DAILY_SALES_SQL).fetchall()
    assert days == sorted(days)
    con.close()
