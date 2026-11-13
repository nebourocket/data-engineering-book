-- 練習問題の答え (events_raw に全パーティションを入れたあとで流す。DuckDB の書き方)

-- 届いた日 (dt) と発生日が違う行の数
SELECT count(*) FROM events_raw WHERE substr(event_time, 1, 10) <> dt;

-- いちばん遅れて届いたデータの遅れ (日数)。date_diff は DuckDB の関数
SELECT max(date_diff('day', CAST(event_time AS DATE), CAST(dt AS DATE))) FROM events_raw;
