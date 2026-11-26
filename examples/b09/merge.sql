-- 標準 SQL の MERGE でも同じ upsert が書けます (PostgreSQL 15 以降、DuckDB 1.4 以降)。
-- 書き方は製品で少し違います。下は DuckDB の例で、* は同名の列を全部使う DuckDB の略記です。
MERGE INTO orders AS t
USING batch AS s
ON t.order_id = s.order_id
WHEN MATCHED THEN UPDATE SET
    customer_id = s.customer_id,
    status = s.status,
    amount = s.amount,
    updated_at = s.updated_at
WHEN NOT MATCHED THEN INSERT *;
