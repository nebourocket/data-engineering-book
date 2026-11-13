# リポジトリの直下で動かします。先に docker compose up -d --wait で MinIO を起動しておきます。
# minioadmin は、この本の compose.yaml の MinIO の初期のユーザー名とパスワードです (手元の学習用)。本番では環境変数や .env から渡し、コードに書きません。
# --network host は、コンテナの中から localhost の MinIO に届かせるためです。結果は work/b16/ にできます。
docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -e S3_ENDPOINT=http://localhost:9000 -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin -v "$PWD":/w -w /w de-book-dev python examples/b16/pipeline.py --dt 2026-07-01 --workdir work/b16
