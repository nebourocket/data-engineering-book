-- name: show_tables
SHOW TABLES;

-- name: describe_products
DESCRIBE products;

-- name: all_rows
SELECT * FROM products;

-- name: pick_columns
SELECT name, price FROM products;

-- name: reorder_columns
SELECT price, name FROM products;

-- name: expression
SELECT name, price, price * 2 AS price_double FROM products;

-- name: alias_quoted
SELECT name AS "商品名", price AS "価格 (円)" FROM products;

-- name: where_eq
SELECT name, category FROM products WHERE category = '飲み物';

-- name: where_cmp
SELECT name, price FROM products WHERE price >= 3000;

-- name: where_ne
SELECT name, category FROM products WHERE category <> '寝具';

-- name: where_and
SELECT name, category, price
FROM products
WHERE category = '寝具' AND price < 5000;

-- name: where_or
SELECT name, category
FROM products
WHERE category = '飲み物' OR category = '雑貨';

-- name: where_not
SELECT name, category FROM products WHERE NOT category = '寝具';

-- name: where_paren
SELECT name, category, price
FROM products
WHERE (category = '飲み物' OR category = '雑貨') AND price < 1000;

-- name: where_no_paren
SELECT name, category, price
FROM products
WHERE category = '飲み物' OR category = '雑貨' AND price < 1000;

-- name: where_in
SELECT name, category FROM products WHERE category IN ('飲み物', '雑貨');

-- name: where_between
SELECT name, price FROM products WHERE price BETWEEN 1200 AND 2800;

-- name: where_like_prefix
SELECT name FROM products WHERE name LIKE 'コーヒー%';

-- name: where_like_inner
SELECT name FROM products WHERE name LIKE '%マ%';

-- name: where_like_one
SELECT name FROM products WHERE name LIKE '紅_';

-- name: string_case
SELECT 'abc' = 'ABC' AS same_text;

-- name: order_asc
SELECT name, price FROM products ORDER BY price;

-- name: order_desc
SELECT name, price FROM products ORDER BY price DESC;

-- name: order_two
SELECT name, category, price
FROM products
ORDER BY category, price DESC;

-- name: limit_top3
SELECT name, price FROM products ORDER BY price DESC LIMIT 3;

-- name: limit_only
SELECT name, price FROM products LIMIT 3;

-- name: full_query
SELECT name, price
FROM products
WHERE category = '飲み物' OR category = '寝具'
ORDER BY price DESC
LIMIT 3;

-- name: lowercase_ok
select name, price from products where category = '雑貨' order by price;

-- name: upper_names
SELECT NAME, PRICE FROM PRODUCTS WHERE PRICE < 500;

-- name: one_line
SELECT name FROM products WHERE price < 1000 ORDER BY price;

-- name: with_comment
-- 高い順に 3 つだけ出す (これはコメントで、実行されません)
SELECT name, price   -- 商品名と価格
FROM products
ORDER BY price DESC  /* 高い順 */
LIMIT 3;
