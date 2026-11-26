-- 部署ごとの「3 月の売上」が、定義の違いで食い違うことを確かめる (semantic.py の HAND_WRITTEN と同じ条件)
SELECT sum(i.quantity * i.unit_price) FROM orders o JOIN order_items i USING (order_id)
WHERE substr(o.ordered_at, 1, 7) = '2026-03' AND o.status <> 'cancelled';
