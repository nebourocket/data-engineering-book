select
    o.order_id,
    o.customer_id,
    o.ordered_at,
    cast(o.ordered_at as date) as order_date,
    o.status,
    t.item_count,
    t.order_amount
from {{ ref('stg_orders') }} as o
inner join {{ ref('int_order_totals') }} as t
    on o.order_id = t.order_id
