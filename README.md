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

## 🤖 AI への注意

- 応用編の本文はこのリポジトリに入れない（非公開リポジトリで管理する）。
- 表は本文に手で打たず CSV に書く。
- 秘密（キーなど）は `wrangler secret` だけに置き、リポジトリに入れない。
