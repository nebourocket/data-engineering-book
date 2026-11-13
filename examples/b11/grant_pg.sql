CREATE ROLE b11_analyst NOLOGIN;
GRANT USAGE ON SCHEMA b11 TO b11_analyst;
GRANT SELECT ON b11.daily_revenue TO b11_analyst;

SET ROLE b11_analyst;
SELECT count(*) AS days FROM b11.daily_revenue;
SELECT count(*) FROM b11.sales_lines;
RESET ROLE;
