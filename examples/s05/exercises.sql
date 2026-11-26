-- name: ex1
SELECT name, stock FROM products WHERE stock <= 10;

-- name: ex2
SELECT name, category, price
FROM products
WHERE category <> '飲み物' AND price >= 1000
ORDER BY price DESC;

-- name: ex3
SELECT name
FROM products
WHERE name LIKE '%コーヒー%' OR name LIKE '__';

-- name: ex4_limit
SELECT name, price FROM products ORDER BY price LIMIT 3;

-- name: ex4_between
SELECT name, price FROM products WHERE price BETWEEN 300 AND 900 ORDER BY price;

-- name: ex5
INSERT INTO products VALUES (10, '三角まくら', '寝具', 2500, 7);

-- name: ex6
SELECT name, price
FROM products
WHERE category = '雑貨'
ORDER BY price DESC
LIMIT 2;
