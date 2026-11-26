"""第16章: 提供の元になる表を作ります。

第10章の dbt モデル (fct_orders と顧客の集計) を、DuckDB の SQL 2 本にまとめた縮小版です。
第11章のウェアハウスの代わりに、手元の DuckDB ファイルを使います。
"""
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import write_duckdb  # noqa: E402

# 集計の基準日。ねぼすけ商店のデータは 2026-01-01 から 180 日分なので、最後の日に合わせます。
AS_OF = "2026-06-30"
# この日数より前に最後の注文がある人を休眠とみなします。
ACTIVE_DAYS = 60

FCT_ORDERS_SQL = """
create or replace table fct_orders as
select
    o.order_id,
    o.customer_id,
    cast(o.ordered_at as timestamp) as ordered_at,
    lower(trim(o.status)) as status,
    t.order_amount
from orders as o
inner join (
    select order_id, sum(quantity * unit_price) as order_amount
    from order_items
    group by order_id
) as t using (order_id)
"""

CUSTOMER_SUMMARY_SQL = """
create or replace table customer_summary as
select
    c.customer_id,
    c.name,
    c.email,
    count(f.order_id) as orders,
    coalesce(sum(f.order_amount), 0) as lifetime_spend,
    max(cast(f.ordered_at as date)) as last_order_date,
    case
        when count(f.order_id) = 0 then 'never'
        when max(cast(f.ordered_at as date)) >= cast(? as date) - ? then 'active'
        else 'dormant'
    end as segment
from customers as c
left join fct_orders as f
    on f.customer_id = c.customer_id and f.status <> 'cancelled'
group by all
"""


def refresh_summary(con: duckdb.DuckDBPyConnection, as_of: str) -> None:
    """基準日を変えて、顧客の集計表を作り直します。"""
    con.execute(CUSTOMER_SUMMARY_SQL, [as_of, ACTIVE_DAYS])


def build_warehouse(path: Path, as_of: str = AS_OF) -> None:
    """生データ (第1章からの共通データ) を入れて、2 つの表を作ります。"""
    write_duckdb(path)
    con = duckdb.connect(str(path))
    try:
        con.execute(FCT_ORDERS_SQL)
        refresh_summary(con, as_of)
    finally:
        con.close()
