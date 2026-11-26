-- name: setup
CREATE TEMP TABLE big AS
SELECT g AS id, g % 1000 AS grp, md5(g::text) AS h
FROM generate_series(1, 2000000) AS g;

-- name: analyze
ANALYZE big;

-- name: plan_before
EXPLAIN SELECT * FROM big WHERE id = 123456;

-- name: create_index
CREATE INDEX big_id ON big (id);

-- name: plan_after
EXPLAIN SELECT * FROM big WHERE id = 123456;

-- name: create_index_grp
CREATE INDEX big_grp ON big (grp);

-- name: plan_low_selectivity
EXPLAIN SELECT * FROM big WHERE grp < 900;

-- name: plan_high_selectivity
EXPLAIN SELECT * FROM big WHERE grp = 7;
