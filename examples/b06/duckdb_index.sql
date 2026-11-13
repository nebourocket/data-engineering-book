-- name: setup
CREATE TABLE big AS
SELECT range AS id, range % 1000 AS grp, md5(CAST(range AS VARCHAR)) AS h
FROM range(2000000)
ORDER BY h;

-- name: scan_before
EXPLAIN ANALYZE SELECT * FROM big WHERE id = 123456;

-- name: create_index
CREATE INDEX big_id ON big (id);

-- name: scan_after
EXPLAIN ANALYZE SELECT * FROM big WHERE id = 123456;

-- name: plan_after
EXPLAIN SELECT * FROM big WHERE id = 123456;

-- name: columns_read
EXPLAIN SELECT avg(id) FROM big WHERE grp = 7;

-- name: sorted_setup
CREATE TABLE big_sorted AS SELECT * FROM big ORDER BY id;

-- name: sorted_scan
EXPLAIN ANALYZE SELECT * FROM big_sorted WHERE id = 123456;
