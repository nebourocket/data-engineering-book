-- 1 行 = 1 日。キャンセルを除いた注文の件数と売上
select
    cast(o.ordered_at as date) as order_date,
    count(distinct o.order_id) as orders,
    sum(i.line_amount) as sales
from {{ ref('stg_orders') }} as o
inner join {{ ref('stg_order_items') }} as i
    on o.order_id = i.order_id
where o.status <> 'cancelled'
group by 1
