# データエンジニアの本

MkDocs Material で作る、データエンジニア向けの本のサイトです（GitHub Pages で公開）。有料の応用編は、あとから Cloudflare Worker 経由で配信します。

## 使い方

`DEV` は開発用イメージでコマンドを動かす短縮です。

```bash
docker build -t de-book-dev .
alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'

DEV mkdocs serve -a 0.0.0.0:8000   # プレビュー（ポートは -p 8000:8000 を付けて公開）
DEV mkdocs build --strict          # 公開前の検証
DEV pytest                         # テスト
```

## サービスを使う章（PostgreSQL・MinIO・Redpanda）

7・9・14・15 章などのコード例は、`compose.yaml` のサービスを使います。環境変数が未設定のテストは skip されます。

```bash
docker compose up -d --wait
docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e PG_DSN=postgresql://deb:deb@localhost:5432/deb \
  -e S3_ENDPOINT=http://localhost:9000 -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin \
  -e KAFKA_BOOTSTRAP=localhost:19092 -e DE_BOOK_REQUIRE_SERVICES=1 \
  -v "$PWD":/w -w /w de-book-dev pytest
docker compose down
```

MinIO は公式イメージの配布が止まったため、固定した旧版（`bitnamilegacy/minio`、更新されないイメージ）を使っています。ローカルの学習用に限ります。

`DE_BOOK_REQUIRE_SERVICES=1` を付けると、環境変数が無いとき skip ではなく失敗にします（CI で使います）。章を書くときは [docs/CHAPTER_GUIDE.md](docs/CHAPTER_GUIDE.md) を読みます。

## 🤖 AI への注意

- 応用編の本文はこのリポジトリに入れない（非公開リポジトリで管理する）。
- 表は本文に手で打たず CSV に書く（`data/tables/` と `{{ table("名前") }}`）。
- 章を書く前に docs/CHAPTER_GUIDE.md を読む。検査は `pytest`（tests/test_chapters.py）。
- 秘密（キーなど）は `wrangler secret` だけに置き、リポジトリに入れない。
