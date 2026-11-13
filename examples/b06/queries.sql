-- name: daily_sales_view
CREATE OR REPLACE TEMP VIEW daily_sales AS
SELECT CAST(o.ordered_at AS DATE) AS d,
       sum(i.quantity * i.unit_price) AS revenue
FROM orders AS o
INNER JOIN order_items AS i USING (order_id)
WHERE lower(o.status) <> 'cancelled'
GROUP BY d;

-- name: daily_sales_shape
SELECT count(*) AS days, min(d) AS first_day, max(d) AS last_day FROM daily_sales;

-- name: row_number_nth
SELECT order_id, customer_id, ordered_at,
       row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at) AS nth
FROM orders
WHERE customer_id = 122
ORDER BY nth;

-- name: rank_compare
SELECT name, price,
       row_number() OVER (ORDER BY price DESC, name) AS rn,
       rank() OVER (ORDER BY price DESC) AS rk,
       dense_rank() OVER (ORDER BY price DESC) AS drk
FROM products
WHERE category = '目覚まし'
ORDER BY price DESC, name;

-- name: lag_gap
SELECT order_id, ordered_at,
       lag(ordered_at) OVER (ORDER BY ordered_at) AS prev_at,
       date_diff('day',
                 CAST(lag(ordered_at) OVER (ORDER BY ordered_at) AS TIMESTAMP),
                 CAST(ordered_at AS TIMESTAMP)) AS days_since_prev
FROM orders
WHERE customer_id = 122
ORDER BY ordered_at;

-- name: running_total
SELECT d, revenue,
       sum(revenue) OVER (ORDER BY d) AS running_total
FROM daily_sales
ORDER BY d
LIMIT 4;

-- name: share_of_total
SELECT category,
       sum(price) AS category_price,
       round(100.0 * sum(price) / sum(sum(price)) OVER (), 1) AS pct
FROM products
GROUP BY category
ORDER BY category_price DESC;

-- name: moving_avg_frames
SELECT d, revenue,
       round(avg(revenue) OVER (ORDER BY d
             ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)) AS avg_rows,
       round(avg(revenue) OVER (ORDER BY d
             RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW)) AS avg_range,
       count(*) OVER (ORDER BY d
             RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW) AS days_in_range
FROM daily_sales
ORDER BY d
LIMIT 10;

-- name: last_value_trap
SELECT d, revenue,
       last_value(revenue) OVER (ORDER BY d) AS default_frame,
       last_value(revenue) OVER (
         ORDER BY d
         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS whole_partition
FROM daily_sales
ORDER BY d
LIMIT 3;

-- name: cte_top_customers
WITH paid AS (
  SELECT * FROM orders WHERE lower(status) <> 'cancelled'
), totals AS (
  SELECT p.customer_id, sum(i.quantity * i.unit_price) AS total
  FROM paid AS p
  INNER JOIN order_items AS i USING (order_id)
  GROUP BY p.customer_id
)
SELECT customer_id, total FROM totals ORDER BY total DESC LIMIT 3;

-- name: recursive_dates
WITH RECURSIVE days(d) AS (
  SELECT DATE '2026-01-01'
  UNION ALL
  SELECT d + 1 FROM days WHERE d < DATE '2026-01-07'
)
SELECT d FROM days;

-- name: gap_fill
WITH RECURSIVE calendar(d) AS (
  SELECT DATE '2026-01-04'
  UNION ALL
  SELECT d + 1 FROM calendar WHERE d < DATE '2026-01-12'
)
SELECT c.d, coalesce(s.revenue, 0) AS revenue
FROM calendar AS c
LEFT JOIN daily_sales AS s ON s.d = c.d
ORDER BY c.d;

-- name: recursive_tree
WITH RECURSIVE staff(id, name, boss_id) AS (
  VALUES (1, '店長', NULL), (2, '発送係長', 1), (3, '発送担当', 2), (4, '問い合わせ担当', 1)
), chain(id, name, depth) AS (
  SELECT id, name, 0 FROM staff WHERE boss_id IS NULL
  UNION ALL
  SELECT s.id, s.name, c.depth + 1
  FROM staff AS s
  INNER JOIN chain AS c ON s.boss_id = c.id
)
SELECT * FROM chain ORDER BY depth, id;

-- name: dup_events
SELECT count(*) AS raw_rows, count(DISTINCT event_id) AS distinct_ids FROM events;

-- name: dedup_events
SELECT count(*) AS n
FROM (
  SELECT *,
         row_number() OVER (PARTITION BY event_id ORDER BY received_at) AS rn
  FROM events
) AS t
WHERE rn = 1;

-- name: dedup_customers_qualify
SELECT count(*) AS n
FROM (
  SELECT *
  FROM customers
  WHERE email IS NOT NULL
  QUALIFY row_number() OVER (PARTITION BY email ORDER BY customer_id) = 1
) AS t;

-- name: latest_order_per_customer
SELECT customer_id, order_id, ordered_at
FROM orders
QUALIFY row_number() OVER (
  PARTITION BY customer_id ORDER BY ordered_at DESC, order_id DESC) = 1
ORDER BY customer_id
LIMIT 3;

-- name: latest_distinct_on
SELECT DISTINCT ON (customer_id) customer_id, order_id, ordered_at
FROM orders
ORDER BY customer_id, ordered_at DESC, order_id DESC
LIMIT 3;

-- name: latest_arg_max
SELECT customer_id, arg_max(order_id, ordered_at) AS order_id
FROM orders
GROUP BY customer_id
ORDER BY customer_id
LIMIT 3;

-- name: sessions_small
WITH e(customer_id, t) AS (
  VALUES (1, TIMESTAMP '2026-05-01 09:00:00'),
         (1, TIMESTAMP '2026-05-01 09:10:00'),
         (1, TIMESTAMP '2026-05-01 09:25:00'),
         (1, TIMESTAMP '2026-05-01 14:00:00'),
         (1, TIMESTAMP '2026-05-01 14:20:00'),
         (2, TIMESTAMP '2026-05-01 09:05:00')
), flagged AS (
  SELECT customer_id, t,
         CASE WHEN t - lag(t) OVER (PARTITION BY customer_id ORDER BY t)
                   > INTERVAL 30 MINUTES THEN 1 ELSE 0 END AS is_new
  FROM e
)
SELECT customer_id, t,
       sum(is_new) OVER (PARTITION BY customer_id ORDER BY t) + 1 AS session_no
FROM flagged
ORDER BY customer_id, t;

-- name: sessions_events
WITH e AS (
  SELECT DISTINCT customer_id, CAST(event_time AS TIMESTAMP) AS t, event_id FROM events
), flagged AS (
  SELECT customer_id, t,
         CASE WHEN t - lag(t) OVER (PARTITION BY customer_id ORDER BY t)
                   > INTERVAL 7 DAYS THEN 1 ELSE 0 END AS is_new
  FROM e
), numbered AS (
  SELECT customer_id,
         sum(is_new) OVER (PARTITION BY customer_id ORDER BY t) + 1 AS session_no
  FROM flagged
)
SELECT count(*) AS sessions
FROM (SELECT DISTINCT customer_id, session_no FROM numbered) AS s;

-- name: pivot_case
SELECT strftime(CAST(ordered_at AS TIMESTAMP), '%Y-%m') AS month,
       count(*) FILTER (WHERE lower(status) = 'placed') AS placed,
       count(*) FILTER (WHERE lower(status) = 'shipped') AS shipped,
       count(*) FILTER (WHERE lower(status) = 'delivered') AS delivered,
       count(*) FILTER (WHERE lower(status) = 'cancelled') AS cancelled
FROM orders
GROUP BY month
ORDER BY month;

-- name: pivot_duckdb
PIVOT (
  SELECT strftime(CAST(ordered_at AS TIMESTAMP), '%Y-%m') AS month,
         lower(status) AS status
  FROM orders
)
ON status
USING count(*)
GROUP BY month
ORDER BY month;

-- name: explain_plan
EXPLAIN
SELECT c.prefecture, sum(i.quantity * i.unit_price) AS revenue
FROM orders AS o
INNER JOIN customers AS c USING (customer_id)
INNER JOIN order_items AS i USING (order_id)
WHERE o.ordered_at >= '2026-03-01'
GROUP BY c.prefecture;

-- name: explain_analyze
EXPLAIN ANALYZE
SELECT c.prefecture, sum(i.quantity * i.unit_price) AS revenue
FROM orders AS o
INNER JOIN customers AS c USING (customer_id)
INNER JOIN order_items AS i USING (order_id)
WHERE o.ordered_at >= '2026-03-01'
GROUP BY c.prefecture;
