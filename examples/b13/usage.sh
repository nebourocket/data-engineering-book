# 第 13 章で打つコマンド (リポジトリの直下で、docker run した開発用イメージの中などで流す)
# 品質確認を流す。error の不合格があると終了コード 1 で止まる。
python examples/b13/quality.py; echo "exit=$?"

# 確認クエリを 1 本ずつ流す (shop.duckdb が無ければ、ねぼすけ商店のデータで作る)
python examples/b05/run_sql.py examples/b13/queries.sql null_ratio dup_emails dup_events
python examples/b05/run_sql.py examples/b13/queries.sql status_values orphans late_events
python examples/b05/run_sql.py examples/b13/queries.sql daily_counts_tail daily_zscore
python examples/b05/run_sql.py examples/b13/queries.sql make_events_ranked make_events_clean make_events_quarantine split_balance
python examples/b05/run_sql.py examples/b13/queries.sql pass_rate_by_dimension failing_since

# dbt のテスト (dbt_demo の中で流す。target/ と logs/ は dbt_demo の下にできる)
cd examples/b13/dbt_demo
SHOP_DB=../../../shop.duckdb dbt test --profiles-dir .

# 標準偏差と Z スコアの手計算の例を出力し、本文の表 (CSV) も書き出す
python examples/b13/zscore_example.py data/tables/b13-zscore-example.csv
