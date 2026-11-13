-- 直した版: 遅れは 4 日までと決め、それを超えた行だけを異常として返す
select event_id, event_time, received_at
from {{ ref('stg_events') }}
where received_at > event_time + interval '4 days'
