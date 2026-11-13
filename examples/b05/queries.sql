-- name: describe_orders
DESCRIBE orders;

-- name: first_orders
SELECT * FROM orders LIMIT 3;

-- name: tokyo
SELECT customer_id, name, prefecture
FROM customers
WHERE prefecture = '東京'
ORDER BY customer_id
LIMIT 5;

-- name: count_tokyo
SELECT count(*) AS n
FROM customers
WHERE prefecture = '東京';

-- name: march_orders
SELECT order_id, ordered_at, status
FROM orders
WHERE status IN ('shipped', 'delivered')
  AND ordered_at >= '2026-03-01'
  AND ordered_at < '2026-04-01'
ORDER BY ordered_at
LIMIT 3;

-- name: like_coffee
SELECT name FROM products WHERE name LIKE '%コーヒー%';

-- name: nulls_order
SELECT customer_id, email
FROM customers
ORDER BY email NULLS FIRST, customer_id
LIMIT 3;

-- name: null_logic
SELECT NULL = NULL AS eq,
       NULL IS NULL AS is_null,
       1 + NULL AS plus,
       NULL AND FALSE AS and_false,
       NULL OR TRUE AS or_true;

-- name: eq_null
SELECT count(*) AS n FROM customers WHERE email = NULL;

-- name: is_null
SELECT count(*) AS n FROM customers WHERE email IS NULL;

-- name: neq_email
SELECT count(*) AS n FROM customers WHERE email <> 'user0001@example.com';

-- name: neq_email_fixed
SELECT count(*) AS n
FROM customers
WHERE email IS DISTINCT FROM 'user0001@example.com';

-- name: count_variants
SELECT count(*) AS all_rows,
       count(email) AS with_email,
       count(DISTINCT email) AS distinct_email
FROM customers;

-- name: not_in_trap
SELECT count(*) AS n
FROM customers
WHERE customer_id NOT IN (SELECT x FROM (VALUES (1), (NULL)) AS t(x));

-- name: not_exists_ok
SELECT count(*) AS n
FROM customers AS c
WHERE NOT EXISTS (
  SELECT 1 FROM (VALUES (1), (NULL)) AS t(x) WHERE t.x = c.customer_id
);

-- name: group_status
SELECT status, count(*) AS n
FROM orders
GROUP BY status
ORDER BY n DESC;

-- name: group_status_lower
SELECT lower(status) AS status, count(*) AS n
FROM orders
GROUP BY lower(status)
ORDER BY n DESC;

-- name: having_pref
SELECT prefecture, count(*) AS n
FROM customers
GROUP BY prefecture
HAVING count(*) >= 55
ORDER BY n DESC;

-- name: revenue_by_category
SELECT p.category,
       count(*) AS lines,
       sum(i.quantity * i.unit_price) AS revenue
FROM order_items AS i
INNER JOIN products AS p ON p.product_id = i.product_id
GROUP BY p.category
ORDER BY revenue DESC;

-- name: left_anti
SELECT c.customer_id, c.name
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;

-- name: left_on_cond
SELECT count(*) AS n
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id AND o.status = 'cancelled';

-- name: left_where_cond
SELECT count(*) AS n
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.status = 'cancelled';

-- name: full_join
SELECT count(*) FILTER (WHERE o.customer_id IS NULL) AS only_customers,
       count(*) FILTER (WHERE c.customer_id IS NULL) AS only_orders,
       count(*) AS total
FROM customers AS c
FULL JOIN orders AS o ON o.customer_id = c.customer_id;

-- name: cross_join
SELECT count(*) AS n
FROM (SELECT DISTINCT prefecture FROM customers) AS a
CROSS JOIN (SELECT DISTINCT category FROM products) AS b;

-- name: fanout_count
SELECT count(*) AS joined_rows,
       count(DISTINCT o.order_id) AS orders
FROM orders AS o
INNER JOIN order_items AS i ON i.order_id = o.order_id;

-- name: fanout_two
SELECT
  (SELECT count(*) FROM orders WHERE customer_id = 122) AS orders_n,
  (SELECT count(*) FROM events WHERE customer_id = 122) AS events_n,
  (SELECT count(*)
     FROM orders AS o
     INNER JOIN events AS e ON e.customer_id = o.customer_id
    WHERE o.customer_id = 122) AS joined_n;

-- name: fanout_fixed
WITH o AS (
  SELECT customer_id, count(*) AS orders_n FROM orders GROUP BY customer_id
), e AS (
  SELECT customer_id, count(*) AS events_n FROM events GROUP BY customer_id
)
SELECT o.customer_id, o.orders_n, e.events_n
FROM o
LEFT JOIN e ON e.customer_id = o.customer_id
WHERE o.customer_id = 122;

-- name: dup_email
SELECT a.customer_id AS id_a, b.customer_id AS id_b, a.email
FROM customers AS a
INNER JOIN customers AS b
  ON a.email = b.email AND a.customer_id < b.customer_id
ORDER BY a.customer_id;

-- name: case_band
SELECT CASE
         WHEN price < 1000 THEN '低価格'
         WHEN price < 3000 THEN '中価格'
         ELSE '高価格'
       END AS band,
       count(*) AS n
FROM products
GROUP BY band
ORDER BY min(price);

-- name: case_status
SELECT sum(CASE WHEN lower(status) = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
       count(*) AS total,
       round(100.0 * sum(CASE WHEN lower(status) = 'cancelled' THEN 1 ELSE 0 END) / count(*), 1) AS cancel_pct
FROM orders;

-- name: typeof_time
SELECT typeof(ordered_at) AS stored_as,
       typeof(CAST(ordered_at AS TIMESTAMP)) AS cast_as
FROM orders
LIMIT 1;

-- name: date_funcs
SELECT CAST(ordered_at AS TIMESTAMP) AS t,
       date_trunc('month', CAST(ordered_at AS TIMESTAMP)) AS month_start,
       CAST(ordered_at AS DATE) + 7 AS plus_7_days
FROM orders
ORDER BY order_id
LIMIT 2;

-- name: monthly_orders
SELECT strftime(CAST(ordered_at AS TIMESTAMP), '%Y-%m') AS month,
       count(*) AS n
FROM orders
GROUP BY month
ORDER BY month;

-- name: late_events
SELECT count(*) AS late_events
FROM events
WHERE CAST(received_at AS TIMESTAMP) - CAST(event_time AS TIMESTAMP) > INTERVAL '1 day';

-- name: alias_where
SELECT price * 2 AS double_price FROM products WHERE double_price > 11000;

-- name: slash
SELECT 7 / 2 AS slash, 7 // 2 AS int_div;

-- name: scalar_sub
SELECT name, price
FROM products
WHERE price > (SELECT avg(price) FROM products)
ORDER BY price DESC
LIMIT 3;

-- name: exists_cancelled
SELECT count(*) AS n
FROM customers AS c
WHERE EXISTS (
  SELECT 1 FROM orders AS o
  WHERE o.customer_id = c.customer_id AND o.status = 'cancelled'
);

-- name: from_sub
SELECT round(avg(n), 2) AS avg_lines_per_order
FROM (
  SELECT order_id, count(*) AS n FROM order_items GROUP BY order_id
) AS per_order;

-- name: union_distinct
SELECT count(*) AS n
FROM (
  SELECT customer_id FROM orders
  UNION
  SELECT customer_id FROM events
) AS u;

-- name: union_all
SELECT count(*) AS n
FROM (
  SELECT customer_id FROM orders
  UNION ALL
  SELECT customer_id FROM events
) AS u;

-- name: coalesce_email
SELECT customer_id, coalesce(email, '(未登録)') AS email
FROM customers
WHERE email IS NULL
ORDER BY customer_id
LIMIT 3;

-- name: nullif_ratio
SELECT customer_id,
       count(*) FILTER (WHERE status = 'cancelled') AS cancelled,
       count(*) FILTER (WHERE lower(status) = 'shipped') AS shipped,
       count(*) FILTER (WHERE status = 'cancelled')
         / nullif(count(*) FILTER (WHERE lower(status) = 'shipped'), 0) AS cancel_per_shipped
FROM orders
WHERE customer_id <= 10
GROUP BY customer_id
ORDER BY customer_id;

-- name: clean_values
SELECT trim('  090-1234-5678 ') AS trimmed,
       replace('090-1234-5678', '-', '') AS digits,
       TRY_CAST('12' AS INTEGER) AS good,
       TRY_CAST('12a' AS INTEGER) AS bad;

-- name: cast_error
SELECT CAST('12a' AS INTEGER) AS n;

-- name: distinct_pref
SELECT DISTINCT prefecture FROM customers ORDER BY prefecture;

-- name: except_customers
SELECT customer_id FROM customers
EXCEPT
SELECT customer_id FROM orders;

-- name: intersect_customers
SELECT count(*) AS n
FROM (
  SELECT customer_id FROM orders
  INTERSECT
  SELECT customer_id FROM events
) AS both_sides;
