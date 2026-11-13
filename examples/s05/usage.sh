alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'
DEV python examples/s05/run_sql.py shop.duckdb examples/s05/create_products.sql
DEV python examples/s05/run_sql.py shop.duckdb examples/s05/queries.sql all_rows
DEV python examples/s05/run_sql.py shop.duckdb examples/s05/queries.sql pick_columns where_eq
DEV python examples/s05/run_sql.py shop.duckdb examples/s05/errors.sql typo_keyword
DEV python examples/s05/run_sql.py shop.duckdb practice.sql
DEV python examples/s05/run_sql.py shop.duckdb try.sql
rm shop.duckdb
