-- 同じキーが複数あるバッチを、キーごとに最新の 1 行にする (第6章の row_number)
-- updated_at まで同じ行が残るなら、連番などの列を ORDER BY に足して順序を一意にする
SELECT order_id, customer_id, status, amount, updated_at FROM (
    SELECT *, row_number() OVER (PARTITION BY order_id ORDER BY updated_at DESC) AS rn
    FROM batch) AS t
WHERE rn = 1
