{{ config(severity='warn') }}
-- 割合の閾値を SQL で書く単発テスト。遅れて届いた行が全体の 5% を超えたときだけ 1 行返す。
select late, total
from (
    select count(*) filter (
               where cast(received_at as timestamp) - cast(event_time as timestamp) >= interval 1 day
           ) as late,
           count(*) as total
    from {{ source('shop', 'events') }}
)
where late > 0.05 * total
