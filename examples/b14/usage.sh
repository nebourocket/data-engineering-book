# 第 14 章で打つコマンド (リポジトリの直下で流す。docker が使える端末が必要)
# python のスクリプトを開発用イメージの中で流すとき (docker のコマンドは手元の端末で流す)
docker run --rm -it --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev bash

# MinIO を起動して、準備ができるまで待つ (リポジトリの直下で)
docker compose up -d --wait

# 入力を作り、ETL のイメージをビルドして、MinIO (localhost:9000) に向けて流す
python examples/b14/make_input.py examples/b14/data/events.jsonl
docker build -t neboske-etl:dev examples/b14/etl
docker run --rm --network host -v "$PWD/examples/b14/data":/data:ro \
  -e S3_ENDPOINT=http://localhost:9000 -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin \
  -e BUCKET=lake-demo -e CREATE_BUCKET=1 neboske-etl:dev

# 後片付け (リポジトリの直下で)。データごと消すときは down -v
docker compose down

# コンテナの中のユーザーを確かめる
docker run --rm --entrypoint id neboske-etl:dev

# ETL と MinIO を compose でまとめて動かす (examples/b14 で)
cd examples/b14
docker compose -f compose.etl.yaml up --build --abort-on-container-exit

# オブジェクトストレージの実演 (MinIO が動いている状態で)
S3_ENDPOINT=http://localhost:9000 S3_ACCESS_KEY=minioadmin S3_SECRET_KEY=minioadmin \
  python examples/b14/demo_storage.py

# 設定ファイルの形の検査を含むテスト
pytest examples/b14

# IAM ポリシーを検査する (examples/b14 の中で)
(cd examples/b14 && python -c "import static_checks as sc; print(sc.policy_problems(open('iam_read_policy.json').read()))")
