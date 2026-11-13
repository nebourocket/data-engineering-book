# 本章のコマンド一覧。リポジトリの直下で、次の順に動かします。
# Docker の開発用イメージ (de-book-dev) の中で動かす場合の短縮:
alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w/examples/b10 de-book-dev'

# 1. 生データ (ねぼすけ商店) を、プロジェクトのフォルダに DuckDB のファイルとして書き出す
DEV python -c "import sys; sys.path.insert(0, '../common'); from neboske_shop import write_duckdb; write_duckdb('neboske.duckdb')"

# 2. 接続の確認と、最初の実行 (profiles.yml は同じフォルダにある)
DEV dbt debug --profiles-dir .
DEV dbt run --profiles-dir .

# 3. 以降のコマンド (DBT_DUCKDB_PATH を渡さなければ neboske.duckdb が使われる)
DEV dbt compile --select stg_orders --profiles-dir .
DEV dbt build --exclude tag:known_issue --profiles-dir .
DEV dbt test --select tag:known_issue --profiles-dir .
DEV dbt build --profiles-dir .
DEV dbt ls --select stg_orders+ --resource-type model --profiles-dir .
DEV dbt build --select fct_daily_sales --full-refresh --profiles-dir .
DEV dbt docs generate --profiles-dir .
