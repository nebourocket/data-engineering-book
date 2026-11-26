-- name: typo_keyword
SELCT name FROM products;

-- name: typo_column
SELECT nmae FROM products;

-- name: typo_table
SELECT name FROM product;

-- name: double_quote
SELECT name FROM products WHERE category = "飲み物";

-- name: fullwidth_quote
SELECT name FROM products WHERE category = ‘飲み物’;

-- name: dangling_and
SELECT name FROM products WHERE price > 1000 AND;

-- name: duplicate_key
INSERT INTO products VALUES (1, '枕 (重複)', '寝具', 3000, 1);

-- name: not_a_number
INSERT INTO products VALUES (10, '三角ベッド', '寝具', 'ten', 1);

-- name: missing_comma
SELECT name price FROM products LIMIT 2;

-- name: create_twice
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name       VARCHAR,
    category   VARCHAR,
    price      INTEGER,
    stock      INTEGER
);
