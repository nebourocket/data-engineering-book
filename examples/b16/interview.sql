-- 面接でよく出る形の SQL。パイプラインを一度動かしたあとの warehouse.duckdb (DuckDB) で動かします。

-- 1. 顧客ごとの最初の注文 (同じ時刻のときは order_id の小さいほう)。標準 SQL の書き方
SELECT customer_id, order_id, ordered_at
FROM (
    SELECT customer_id, order_id, ordered_at,
           row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at, order_id) AS rn
    FROM analytics.stg_orders
) AS t
WHERE rn = 1
ORDER BY customer_id;

-- 2. 日別売上の「直近 7 行」の平均。注文の無い日は行が無いので、7 行は 7 日とは限らない
SELECT order_date, sales,
       avg(sales) OVER (ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS avg_last_7_rows
FROM analytics.fct_daily_sales
ORDER BY order_date;

-- 3. 検算: 注文の件数が、明細の無い注文を含めて合っているか (JOIN で行が消えていないか)
SELECT (SELECT count(*) FROM analytics.stg_orders) AS orders,
       (SELECT count(DISTINCT order_id) FROM main.order_items) AS orders_with_items;

-- 4. 1. と同じ結果を QUALIFY で書く。DuckDB の書き方で、標準 SQL や PostgreSQL では動かない
SELECT customer_id, order_id, ordered_at
FROM analytics.stg_orders
QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at, order_id) = 1
ORDER BY customer_id;
