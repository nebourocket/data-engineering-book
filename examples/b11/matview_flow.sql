SELECT sum(revenue) AS revenue FROM b11.daily_revenue;

INSERT INTO b11.sales_lines VALUES (999999, '2026-03-01 10:00:00', 1, 1000);

SELECT sum(revenue) AS revenue FROM b11.daily_revenue;

REFRESH MATERIALIZED VIEW CONCURRENTLY b11.daily_revenue;

SELECT sum(revenue) AS revenue FROM b11.daily_revenue;
