# ドキュメントのサイトを Docker の中で動かすときは、外から見えるように host を開け、ポートを公開する
docker run --rm -p 8080:8080 --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w/examples/b10 de-book-dev dbt docs serve --host 0.0.0.0 --port 8080 --profiles-dir .
