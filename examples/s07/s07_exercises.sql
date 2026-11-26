-- name: ex5
SELECT prefecture, count(DISTINCT order_id) AS orders, sum(price * quantity) AS total
FROM order_items
GROUP BY prefecture
ORDER BY prefecture;
