-- 状態の表記ゆれ (shipped / SHIPPED) を小文字にそろえ、日時を型にする
select
    order_id,
    customer_id,
    cast(ordered_at as timestamp) as ordered_at,
    lower(status) as status
from {{ source('raw', 'orders') }}
