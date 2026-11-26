DROP SCHEMA IF EXISTS b11 CASCADE;
CREATE SCHEMA b11;

CREATE TABLE b11.sales_lines (order_id int, ordered_at timestamp, quantity int, unit_price int);

-- 3 月の 31 日分に、3,000 明細を決まった規則で入れる（乱数を使わないので、いつも同じ値になる）
INSERT INTO b11.sales_lines
SELECT n, timestamp '2026-03-01' + (n % 31) * interval '1 day', 1 + n % 3, 500 + (n % 7) * 100
FROM generate_series(1, 3000) AS n;

CREATE MATERIALIZED VIEW b11.daily_revenue AS
SELECT CAST(ordered_at AS date) AS d, sum(quantity * unit_price) AS revenue
FROM b11.sales_lines
GROUP BY 1;

CREATE UNIQUE INDEX daily_revenue_d ON b11.daily_revenue (d);
