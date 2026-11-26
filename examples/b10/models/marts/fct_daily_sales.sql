{{
    config(
        materialized='incremental',
        unique_key='order_date',
        incremental_strategy='delete+insert'
    )
}}

select
    order_date,
    count(*) as orders,
    sum(order_amount) as sales
from {{ ref('fct_orders') }}
where status <> 'cancelled'
{% if is_incremental() %}
  and order_date >= (
      select {{ dbt.dateadd('day', -7, 'max(order_date)') }} from {{ this }}
  )
{% endif %}
group by order_date
