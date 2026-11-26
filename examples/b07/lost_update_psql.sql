-- psql を 2 つ開いて、端末 1 と端末 2 の行を、番号の順に打ちます（接続: psql "$PG_DSN"）。
-- 準備（端末 1）
SET search_path TO b07;
CREATE TABLE IF NOT EXISTS stock_psql (product_id int PRIMARY KEY, quantity int NOT NULL);
INSERT INTO stock_psql VALUES (1, 10) ON CONFLICT (product_id) DO UPDATE SET quantity = 10;

-- 1. 端末 1: BEGIN; SELECT quantity FROM stock_psql WHERE product_id = 1;   -- 10 が見える
-- 2. 端末 2: SET search_path TO b07; BEGIN; SELECT quantity FROM stock_psql WHERE product_id = 1;   -- 10 が見える
-- 3. 端末 1: UPDATE stock_psql SET quantity = 7 WHERE product_id = 1; COMMIT;   -- 10 - 3
-- 4. 端末 2: UPDATE stock_psql SET quantity = 8 WHERE product_id = 1; COMMIT;   -- 10 - 2。端末 1 の更新が消える
-- 5. どちらの端末でも: SELECT quantity FROM stock_psql WHERE product_id = 1;   -- 8（正しくは 5）
-- 直すには、先頭の「準備」をもう一度打って在庫を 10 に戻し、1 と 2 の BEGIN を
-- BEGIN ISOLATION LEVEL REPEATABLE READ; にして、1 から 5 をやり直す（端末 2 は SET search_path から）。
-- 4 でエラー（could not serialize access due to concurrent update）になり、端末 2 は ROLLBACK してやり直す。
