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
