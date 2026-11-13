-- name: ddl_create_as
CREATE TABLE my_products AS
SELECT product_id, name, price FROM products WHERE category = '飲み物';

-- name: ddl_count
SELECT count(*) AS n FROM my_products;

-- name: ddl_insert
INSERT INTO my_products VALUES (999, 'テスト商品', 100);

-- name: ddl_update
UPDATE my_products SET price = price + 100 WHERE product_id = 999;

-- name: ddl_check
SELECT product_id, name, price FROM my_products WHERE product_id = 999;

-- name: ddl_delete
DELETE FROM my_products WHERE product_id = 999;

-- name: ddl_view
CREATE VIEW cheap_products AS
SELECT product_id, name, price FROM products WHERE price < 1000;

-- name: ddl_view_count
SELECT count(*) AS n FROM cheap_products;

-- name: ddl_create_table
CREATE TABLE memo (id INTEGER PRIMARY KEY, body VARCHAR NOT NULL);

-- name: ddl_duplicate_key_error
INSERT INTO memo VALUES (1, 'one'), (1, 'two');
