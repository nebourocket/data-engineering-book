-- 注文ごとの合計の総和が、明細の総和と一致しないとき、その差の 1 行を返す (返れば失敗)
with totals as (
    select
        (select sum(order_amount) from {{ ref('fct_orders') }}) as orders_total,
        (select sum(line_amount) from {{ ref('stg_order_items') }}) as items_total
)

select orders_total, items_total
from totals
where orders_total <> items_total
