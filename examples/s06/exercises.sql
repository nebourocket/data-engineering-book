-- name: ex1
SELECT count(*) AS n, sum(amount) AS total FROM orders WHERE amount >= 2000;

-- name: ex2
SELECT customer_id, max(amount) AS largest
FROM orders
GROUP BY customer_id
ORDER BY customer_id;

-- name: ex3
SELECT customer_id, sum(amount) AS total
FROM orders
GROUP BY customer_id
HAVING sum(amount) >= 5000
ORDER BY customer_id;

-- name: ex4
SELECT c.name, o.order_id, o.amount
FROM customers AS c
INNER JOIN orders AS o ON o.customer_id = c.customer_id
WHERE c.prefecture = '東京'
ORDER BY o.order_id;

-- name: ex5
SELECT prefecture, count(*) AS n, avg(points) AS average_points
FROM customers
GROUP BY prefecture
ORDER BY prefecture;

-- name: ex6
SELECT order_id, amount
FROM orders
WHERE amount = (SELECT max(amount) FROM orders);

-- name: ex7
SELECT c.name, c.prefecture
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;

-- name: ex8
SELECT c.name, count(o.order_id) AS n
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
GROUP BY c.name
ORDER BY n DESC, c.name;

-- name: ex9
SELECT c.name, sum(o.amount) AS total
FROM customers AS c
INNER JOIN orders AS o ON o.customer_id = c.customer_id
GROUP BY c.name
HAVING sum(o.amount) >= 5000
ORDER BY c.name;
