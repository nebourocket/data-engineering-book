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
