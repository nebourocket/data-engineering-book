-- ねぼすけ商店の品質確認クエリ。run_sql.py (第 5 章) で流します。
-- 使い方: python examples/b05/run_sql.py examples/b13/queries.sql null_ratio dup_emails

-- name: null_ratio
SELECT count(*) AS total,
       count(*) FILTER (WHERE email IS NULL) AS null_emails,
       round(100.0 * count(*) FILTER (WHERE email IS NULL) / count(*), 2) AS null_pct
FROM customers;

-- name: dup_emails
SELECT email, count(*) AS n, list(customer_id ORDER BY customer_id) AS customer_ids
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING count(*) > 1
ORDER BY email;

-- name: dup_events
SELECT count(*) AS total, count(DISTINCT event_id) AS distinct_ids,
       count(*) - count(DISTINCT event_id) AS excess_rows
FROM events;

-- name: status_values
SELECT status, count(*) AS n FROM orders GROUP BY status ORDER BY n DESC;

-- name: orphans
SELECT count(*) AS orphan_orders
FROM orders AS o
LEFT JOIN customers AS c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;

-- name: late_events
SELECT count(*) FILTER (WHERE CAST(received_at AS TIMESTAMP) - CAST(event_time AS TIMESTAMP)
                              >= INTERVAL 1 DAY) AS late_rows,
       count(*) AS total
FROM events;

-- name: daily_counts_tail
WITH daily AS (
    SELECT CAST(event_time AS DATE) AS d, count(*) AS n FROM events GROUP BY d
)
SELECT d, n,
       lag(n) OVER (ORDER BY d) AS prev_n,
       round(n / lag(n) OVER (ORDER BY d), 2) AS ratio_to_prev
FROM daily
ORDER BY d DESC
LIMIT 3;

-- name: daily_zscore
WITH daily AS (
    SELECT CAST(event_time AS DATE) AS d, count(*) AS n FROM events GROUP BY d
),
scored AS (
    SELECT d, n,
           avg(n) OVER w AS mu,
           stddev_samp(n) OVER w AS sd
    FROM daily
    WINDOW w AS (ORDER BY d ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING)
)
SELECT d, n, round(mu, 1) AS mu, round((n - mu) / sd, 2) AS z
FROM scored
WHERE abs((n - mu) / sd) > 3
ORDER BY d;

-- name: make_events_clean
CREATE OR REPLACE TABLE events_clean AS
SELECT event_id, customer_id, event_type, event_time, received_at
FROM (
    SELECT *, row_number() OVER (PARTITION BY event_id ORDER BY received_at) AS rn
    FROM events
)
WHERE rn = 1;

-- name: make_events_quarantine
CREATE OR REPLACE TABLE events_quarantine AS
SELECT event_id, customer_id, event_type, event_time, received_at,
       'duplicate_event_id' AS reason
FROM (
    SELECT *, row_number() OVER (PARTITION BY event_id ORDER BY received_at) AS rn
    FROM events
)
WHERE rn > 1;

-- name: split_balance
SELECT (SELECT count(*) FROM events) AS raw_rows,
       (SELECT count(*) FROM events_clean) AS clean_rows,
       (SELECT count(*) FROM events_quarantine) AS quarantined_rows;

-- name: pass_rate_by_dimension
SELECT dimension,
       count(*) AS checks,
       count(*) FILTER (WHERE passed) AS passed,
       round(100.0 * count(*) FILTER (WHERE passed) / count(*), 1) AS pass_pct
FROM dq_results
WHERE run_id = (SELECT run_id FROM dq_results ORDER BY run_at DESC LIMIT 1)
GROUP BY dimension
ORDER BY dimension;

-- name: failing_since
SELECT check_name, severity, min(run_at) AS first_seen, count(*) AS failed_runs
FROM dq_results
WHERE NOT passed
GROUP BY check_name, severity
ORDER BY first_seen, check_name;

-- name: status_values_lowered
SELECT count(*) AS still_bad
FROM orders
WHERE lower(status) NOT IN ('placed', 'shipped', 'delivered', 'cancelled');
