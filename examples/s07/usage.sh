alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'
DEV python examples/s07/s07_wide_long.py
DEV python examples/s07/s07_csv_quote.py
DEV python examples/s07/s07_csv_encoding.py
DEV python examples/s07/s07_csv_types.py
DEV python examples/s07/s07_json_basics.py
DEV python examples/s07/s07_flatten.py
DEV python examples/s07/s07_three_views.py
DEV python examples/s07/s07_orders_sql.py
