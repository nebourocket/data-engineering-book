-- 受信時刻が発生時刻より前の行があれば返す (返れば失敗)
select event_id, event_time, received_at
from {{ ref('stg_events') }}
where received_at < event_time
