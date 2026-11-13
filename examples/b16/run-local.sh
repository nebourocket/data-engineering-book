# サービスなしで、手元のフォルダ (work/b16/landing/) に置いて動かす場合です。S3_ENDPOINT を渡さないので MinIO は使いません。
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev python examples/b16/pipeline.py --dt 2026-07-01 --workdir work/b16
