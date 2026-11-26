-- postgresql.conf (変更後に PostgreSQL の再起動が要ります)
-- wal_level = logical
-- max_replication_slots = 10
-- max_wal_senders = 10

-- 変更を配る範囲 (publication) を決める
CREATE PUBLICATION dbz_orders FOR TABLE orders, order_items;

-- 読み手専用の役割。REPLICATION 属性と、対象表の SELECT だけを持たせる
CREATE ROLE debezium WITH LOGIN REPLICATION PASSWORD 'change-me';
GRANT SELECT ON orders, order_items TO debezium;

-- 更新・削除のときに「変更前の行」をどこまで WAL に入れるか
ALTER TABLE orders REPLICA IDENTITY FULL;

-- スロットを作る (test_decoding は読み物用、pgoutput が実運用の標準)
SELECT pg_create_logical_replication_slot('demo_slot', 'test_decoding');
SELECT * FROM pg_logical_slot_peek_changes('demo_slot', NULL, NULL);
SELECT * FROM pg_logical_slot_get_changes('demo_slot', NULL, NULL);
SELECT pg_drop_replication_slot('demo_slot');

-- スロットが止めている WAL を見張る
SELECT slot_name, active, wal_status, safe_wal_size,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained
FROM pg_replication_slots;

-- スロットが止められる WAL の上限 (PostgreSQL 13 以降。超えるとスロットは lost になる)
ALTER SYSTEM SET max_slot_wal_keep_size = '50GB';
SELECT pg_reload_conf();

-- 更新の少ない表だけを読むコネクタのために、ハートビート用の表へ書く (heartbeat.action.query で指定する)
CREATE TABLE debezium_heartbeat (id integer PRIMARY KEY, beat timestamptz);
INSERT INTO debezium_heartbeat VALUES (1, now());
UPDATE debezium_heartbeat SET beat = now() WHERE id = 1;

-- outbox の掃除: 送信済みで一定時間たった行を消す
DELETE FROM outbox WHERE sent_at < now() - interval '7 days';

-- PostgreSQL 15 以降の MERGE (DWH 側が PostgreSQL のときの書き方)
MERGE INTO dim_orders AS t
USING latest_changes AS s ON t.order_id = s.order_id
WHEN MATCHED AND s.op = 'd' THEN DELETE
WHEN MATCHED THEN UPDATE SET status = s.status, amount = s.amount
WHEN NOT MATCHED AND s.op <> 'd' THEN INSERT (order_id, status, amount) VALUES (s.order_id, s.status, s.amount);
