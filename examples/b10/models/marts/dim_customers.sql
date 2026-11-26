select
    c.customer_id,
    c.name,
    c.email,
    c.prefecture,
    coalesce(r.region, '不明') as region,
    c.registered_at
from {{ ref('stg_customers') }} as c
left join {{ ref('prefecture_region') }} as r
    on c.prefecture = r.prefecture
