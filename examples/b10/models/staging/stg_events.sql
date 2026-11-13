with ranked as (
    select
        *,
        row_number() over (
            partition by event_id
            order by received_at, event_time, customer_id, event_type
        ) as rn
    from {{ source('raw', 'events') }}
)

select
    event_id,
    customer_id,
    event_type,
    cast(event_time as timestamp) as event_time,
    cast(received_at as timestamp) as received_at
from ranked
where rn = 1
