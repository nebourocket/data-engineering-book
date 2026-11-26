# 第 7 章のコード例

PostgreSQL が必要です（リポジトリのルートで `docker compose up -d --wait`）。接続先は環境変数 `PG_DSN` で渡します。コードはスキーマ `b07` を作り直して使います。

```bash
export PG_DSN=postgresql://deb:deb@localhost:5432/deb
cd examples/b07
python normalization.py
python constraints.py
python anomalies.py
python locks.py
python safe_read.py
python acid.py
```

`psycopg` は `pip install "psycopg[binary]"` で入ります。Docker で動かすなら、リポジトリのルートで `docker build -t de-book-dev .` したイメージに、`--network host` と `-e PG_DSN=...` を付けて同じコマンドを実行します。

`lost_update_psql.sql` は、psql を 2 つ開いて手で更新の消失を起こす手順です。

テストはどれも同じスキーマ `b07` を作り直して使うので、並べて（並列に）動かさないでください。
