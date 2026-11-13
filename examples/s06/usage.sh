alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'
DEV python examples/s05/run_sql.py shop.duckdb examples/s06/setup.sql
DEV python examples/s05/run_sql.py shop.duckdb examples/s06/queries.sql aggregates
DEV python examples/s05/run_sql.py shop.duckdb examples/s06/queries.sql group_by
rm shop.duckdb
