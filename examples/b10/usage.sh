# 本章のコマンド一覧。プロジェクトのフォルダ (examples/b10) で動かします。
# 生データは examples/common/neboske_shop.py の write_duckdb で作った DuckDB ファイルです。
export DBT_DUCKDB_PATH=/work/neboske.duckdb

# 生データの用意 (リポジトリの直下で)
python -c "import sys; sys.path.insert(0, 'examples/common'); from neboske_shop import write_duckdb; write_duckdb('/work/neboske.duckdb')"

dbt compile --select stg_orders --profiles-dir .
dbt build --exclude tag:known_issue --profiles-dir .
dbt test --select tag:known_issue --profiles-dir .
dbt build --profiles-dir .
dbt ls --select stg_orders+ --resource-type model --profiles-dir .
dbt build --select fct_daily_sales --full-refresh --profiles-dir .
dbt docs generate --profiles-dir .
dbt docs serve --profiles-dir .
