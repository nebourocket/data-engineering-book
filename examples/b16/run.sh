# リポジトリの直下で動かします。MinIO を使うなら docker compose up -d --wait で起動しておきます。
# MinIO に置く場合 (S3_ENDPOINT を渡す)。--network host は、コンテナから localhost の MinIO に届かせるためです。
docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -e S3_ENDPOINT=http://localhost:9000 -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin -v "$PWD":/w -w /w de-book-dev python examples/b16/pipeline.py --dt 2026-07-01 --workdir work/b16

# サービスなしで、手元のフォルダに置く場合 (S3_ENDPOINT を渡さない)
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev python examples/b16/pipeline.py --dt 2026-07-01 --workdir work/b16
