select
    order_id,
    count(*) as item_count,
    sum(line_amount) as order_amount
from {{ ref('stg_order_items') }}
group by order_id
