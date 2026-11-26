alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'
DEV python examples/s08/s08_trace.py
DEV python examples/s08/s08_err_file.py
DEV python examples/s08/s08_err_import.py
DEV python examples/s08/s08_err_index.py
DEV python examples/s08/s08_err_attribute.py
DEV python examples/s08/s08_err_json.py
DEV python examples/s08/s08_err_port.py
DEV python examples/s08/s08_err_duckdb.py
DEV python examples/s08/s08_bug_before.py
DEV python examples/s08/s08_bug_prints.py
DEV python examples/s08/s08_bug_fixed.py
DEV python examples/s08/s08_minimal.py
DEV python --version
DEV python -c "import duckdb; print(duckdb.__version__)"
DEV python examples/s08/s08_ex_range.py
DEV python examples/s08/s08_ex_average.py
DEV python examples/s08/s08_ex_ai.py
docker run -d --rm --name s08-web -p 18080:8000 de-book-dev python -m http.server 8000
docker run --rm -p 18080:8000 de-book-dev python -m http.server 8000
docker ps
docker stop s08-web
