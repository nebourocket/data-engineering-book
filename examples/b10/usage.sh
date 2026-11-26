# 本章のコマンド一覧。リポジトリの直下で、次の順に動かします。
# Docker の開発用イメージ (de-book-dev) の中で動かす場合の短縮 (関数) と、生データ (ねぼすけ商店) の書き出し。
dev() { docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w/examples/b10 de-book-dev "$@"; }
dbt() { dev dbt "$@"; }
dev python -c "import sys; sys.path.insert(0, '../common'); from neboske_shop import write_duckdb; write_duckdb('neboske.duckdb')"

# 接続の確認、seed (対応表) の取り込み、全 model の実行。seed が無いと dim_customers が失敗する
dbt debug --profiles-dir .
dbt seed --profiles-dir .
dbt run --profiles-dir .

# 以降のコマンド (DBT_DUCKDB_PATH を渡さなければ neboske.duckdb が使われる)
dbt compile --select stg_orders --profiles-dir .
dbt build --exclude tag:known_issue --profiles-dir .
dbt test --select tag:known_issue --profiles-dir .
dbt build --profiles-dir .
dbt ls --select stg_orders+ --resource-type model --profiles-dir .
dbt build --select fct_daily_sales --full-refresh --profiles-dir .
dbt docs generate --profiles-dir .
