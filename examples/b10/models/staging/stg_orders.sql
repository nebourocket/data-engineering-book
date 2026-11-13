select
    order_id,
    customer_id,
    cast(ordered_at as timestamp) as ordered_at,
    {{ clean_text('status') }} as status
from {{ source('raw', 'orders') }}
