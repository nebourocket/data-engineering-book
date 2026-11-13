-- name: create_mv
CREATE MATERIALIZED VIEW b11.daily_revenue AS
SELECT CAST(ordered_at AS date) AS d, sum(quantity * unit_price) AS revenue
FROM b11.sales_lines
GROUP BY 1;

CREATE UNIQUE INDEX daily_revenue_d ON b11.daily_revenue (d);

-- name: refresh_mv
REFRESH MATERIALIZED VIEW CONCURRENTLY b11.daily_revenue;

-- name: grant_mv
CREATE ROLE b11_analyst NOLOGIN;
GRANT USAGE ON SCHEMA b11 TO b11_analyst;
GRANT SELECT ON b11.daily_revenue TO b11_analyst;
