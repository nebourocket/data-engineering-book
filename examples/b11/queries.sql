-- name: full_scan
SELECT sum(quantity * unit_price) AS revenue
FROM sales;

-- name: month_filter
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE month = '2026-03';

-- name: date_filter_only
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE ordered_at >= '2026-03-01' AND ordered_at < '2026-04-01';

-- name: select_star
SELECT *
FROM sales
WHERE month = '2026-03';

-- name: explain_month
EXPLAIN ANALYZE
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE month = '2026-03';

-- name: explain_date_filter
EXPLAIN ANALYZE
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE ordered_at >= '2026-03-01' AND ordered_at < '2026-04-01';

-- name: monthly_partial
SELECT month, sum(quantity * unit_price) AS revenue, count(*) AS n
FROM sales
GROUP BY month
ORDER BY month;

-- name: combine_partials
SELECT sum(revenue) AS revenue,
       sum(revenue) / sum(n) AS avg_line,
       avg(revenue / n) AS avg_of_avgs
FROM (
  SELECT month, sum(quantity * unit_price) AS revenue, count(*) AS n
  FROM sales
  GROUP BY month
) AS partial;

-- name: direct_total
SELECT sum(quantity * unit_price) AS revenue,
       avg(quantity * unit_price) AS avg_line
FROM sales;

-- name: ex_one_day_with_month
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE month = '2026-03'
  AND ordered_at >= '2026-03-05' AND ordered_at < '2026-03-06';

-- name: ex_one_day_only
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE ordered_at >= '2026-03-05' AND ordered_at < '2026-03-06';

-- name: month_wrapped
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE substr(month, 1, 7) = '2026-03';

-- name: load_into_table
CREATE TABLE sales_loaded AS
SELECT * FROM sales WHERE month = '2026-03';

-- name: ex_incremental
CREATE TABLE monthly AS
SELECT month, sum(quantity * unit_price) AS revenue, count(*) AS n
FROM sales
GROUP BY month;

CREATE TABLE new_day AS
SELECT '2026-06' AS month, 12000 AS revenue, 3 AS n;

UPDATE monthly
SET revenue = monthly.revenue + new_day.revenue, n = monthly.n + new_day.n
FROM new_day
WHERE monthly.month = new_day.month;

SELECT month, revenue, n, revenue / n AS avg_line FROM monthly WHERE month = '2026-06';

-- name: ex_distinct
SELECT sum(customers) AS sum_of_monthly, (SELECT count(DISTINCT customer_id) FROM sales) AS overall
FROM (
  SELECT month, count(DISTINCT customer_id) AS customers
  FROM sales
  GROUP BY month
) AS monthly_customers;
