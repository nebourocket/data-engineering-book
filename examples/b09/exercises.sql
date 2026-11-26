-- 練習問題の答え (events_raw に全パーティションを入れたあとで流す。DuckDB の書き方)
-- 1 つ目: 届いた日 (dt) と発生日が違う行の数。2 つ目: いちばん遅れて届いた行の遅れ (日数)。
-- date_diff は DuckDB の関数
SELECT count(*) FROM events_raw WHERE substr(event_time, 1, 10) <> dt;
SELECT max(date_diff('day', CAST(event_time AS DATE), CAST(dt AS DATE))) FROM events_raw;
