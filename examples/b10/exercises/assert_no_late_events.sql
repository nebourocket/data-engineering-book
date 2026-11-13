-- 最初の版 (失敗する): 遅れて届いたイベントが 1 件もないはず、と決めつけた
select event_id, event_time, received_at
from {{ ref('stg_events') }}
where cast(received_at as date) > cast(event_time as date)
