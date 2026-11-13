-- name: all_customers
SELECT * FROM customers;

-- name: all_orders
SELECT * FROM orders;

-- name: count_all
SELECT count(*) AS n FROM orders;

-- name: aggregates
SELECT count(*) AS n,
       sum(amount) AS total,
       min(amount) AS smallest,
       max(amount) AS largest
FROM orders;

-- name: average
SELECT avg(amount) AS average, round(avg(amount), 1) AS rounded FROM orders;

-- name: sum_where
SELECT sum(amount) AS total FROM orders WHERE customer_id = 3;

-- name: group_by
SELECT customer_id, count(*) AS n, sum(amount) AS total
FROM orders
GROUP BY customer_id
ORDER BY customer_id;

-- name: group_by_where
SELECT customer_id, count(*) AS n, sum(amount) AS total
FROM orders
WHERE amount >= 1000
GROUP BY customer_id
ORDER BY customer_id;

-- name: group_by_having
SELECT customer_id, count(*) AS n, sum(amount) AS total
FROM orders
GROUP BY customer_id
HAVING count(*) >= 2
ORDER BY customer_id;

-- name: where_and_having
SELECT customer_id, count(*) AS n, sum(amount) AS total
FROM orders
WHERE amount >= 1000
GROUP BY customer_id
HAVING count(*) >= 2
ORDER BY customer_id;

-- name: group_by_wrong
SELECT customer_id, amount FROM orders GROUP BY customer_id;

-- name: where_aggregate_wrong
SELECT customer_id FROM orders WHERE count(*) >= 2 GROUP BY customer_id;

-- name: join_inner
SELECT c.customer_id, c.name, o.order_id, o.amount
FROM customers AS c
INNER JOIN orders AS o ON o.customer_id = c.customer_id
ORDER BY o.order_id;

-- name: join_left
SELECT c.customer_id, c.name, o.order_id, o.amount
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;

-- name: join_counts
SELECT (SELECT count(*) FROM customers) AS customers_rows,
       (SELECT count(*) FROM orders) AS orders_rows,
       (SELECT count(*)
        FROM customers AS c
        INNER JOIN orders AS o ON o.customer_id = c.customer_id) AS inner_rows,
       (SELECT count(*)
        FROM customers AS c
        LEFT JOIN orders AS o ON o.customer_id = c.customer_id) AS left_rows;

-- name: join_no_orders
SELECT c.name
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;

-- name: join_group
SELECT c.name, count(o.order_id) AS n, sum(o.amount) AS total
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
GROUP BY c.name
ORDER BY c.name;

-- name: join_ambiguous
SELECT customer_id FROM customers AS c INNER JOIN orders AS o ON o.customer_id = c.customer_id;

-- name: null_show
SELECT customer_id, email, points FROM customers;

-- name: null_arith
SELECT 1 + NULL AS plus, NULL = NULL AS equal, NULL IS NULL AS is_null;

-- name: null_equal_wrong
SELECT name FROM customers WHERE email = NULL;

-- name: null_is
SELECT name FROM customers WHERE email IS NULL;

-- name: null_not
SELECT name FROM customers WHERE email IS NOT NULL;

-- name: empty_string
SELECT name FROM customers WHERE email = '';

-- name: null_vanishes_ge
SELECT name, points FROM customers WHERE points >= 200;

-- name: null_vanishes_lt
SELECT name, points FROM customers WHERE points < 200;

-- name: count_variants
SELECT count(*) AS all_rows, count(email) AS with_email, count(points) AS with_points
FROM customers;

-- name: avg_points
SELECT avg(points) AS average, sum(points) AS total, count(points) AS n FROM customers;

-- name: coalesce_points
SELECT avg(coalesce(points, 0)) AS average_with_zero FROM customers;

-- name: subquery_scalar
SELECT order_id, amount
FROM orders
WHERE amount > (SELECT avg(amount) FROM orders)
ORDER BY order_id;

-- name: subquery_in
SELECT name
FROM customers
WHERE customer_id IN (SELECT customer_id FROM orders)
ORDER BY customer_id;

-- name: subquery_from
SELECT max(total) AS best_total
FROM (SELECT customer_id, sum(amount) AS total FROM orders GROUP BY customer_id) AS per_customer;
