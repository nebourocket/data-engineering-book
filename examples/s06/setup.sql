CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        VARCHAR,
    prefecture  VARCHAR,
    email       VARCHAR,
    points      INTEGER
);

INSERT INTO customers VALUES
    (1, '佐藤 太郎', '東京', 'taro@example.com', 100),
    (2, '鈴木 花子', '大阪', '', 300),
    (3, '高橋 健', '東京', NULL, NULL),
    (4, '田中 美咲', '石川', 'misaki@example.com', 200);

CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER,
    amount      INTEGER
);

INSERT INTO orders VALUES
    (101, 1, 3200),
    (102, 1, 900),
    (103, 2, 5800),
    (104, 3, 1200),
    (105, 3, 2800),
    (106, 3, 1500);
