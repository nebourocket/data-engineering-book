-- name: ex1_top2_per_category
SELECT category, name, price
FROM (
  SELECT category, name, price,
         row_number() OVER (PARTITION BY category ORDER BY price DESC, name) AS rn
  FROM products
) AS t
WHERE rn <= 2
ORDER BY category, price DESC, name;

-- name: ex2_avg_gap
WITH gaps AS (
  SELECT date_diff('day',
           CAST(lag(ordered_at) OVER (PARTITION BY customer_id ORDER BY ordered_at) AS TIMESTAMP),
           CAST(ordered_at AS TIMESTAMP)) AS days
  FROM orders
)
SELECT count(days) AS gaps, round(avg(days), 1) AS avg_days FROM gaps;

-- name: ex3_second_order
SELECT count(*) AS customers_with_2plus_orders
FROM (
  SELECT customer_id
  FROM orders
  QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at, order_id) = 2
) AS t;

-- name: ex4_dedup_by_type
WITH dedup AS (
  SELECT *
  FROM events
  QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY received_at) = 1
)
SELECT event_type, count(*) AS n FROM dedup GROUP BY event_type ORDER BY n DESC;
