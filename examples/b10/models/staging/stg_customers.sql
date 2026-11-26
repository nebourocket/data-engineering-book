select
    customer_id,
    name,
    {{ clean_text('email') }} as email,
    prefecture,
    cast(registered_at as timestamp) as registered_at
from {{ source('raw', 'customers') }}
