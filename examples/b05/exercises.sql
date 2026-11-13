-- name: ex2_dup_registrations
SELECT email, count(*) AS n
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING count(*) >= 2
ORDER BY email;

-- name: ex2_null_group
SELECT count(*) AS n
FROM customers
WHERE email IS NULL
GROUP BY email;

-- name: ex4_half_open
SELECT count(*) FROM orders
WHERE ordered_at >= '2026-06-01' AND ordered_at < '2026-07-01';

-- name: ex4_between
SELECT count(*) FROM orders
WHERE ordered_at BETWEEN '2026-06-01' AND '2026-06-30';

-- name: ex4_last_order
SELECT max(ordered_at) AS last_order FROM orders;

-- name: ex3_never_cancelled
SELECT count(*) AS n
FROM customers AS c
WHERE NOT EXISTS (
  SELECT 1 FROM orders AS o
  WHERE o.customer_id = c.customer_id AND o.status = 'cancelled'
);
