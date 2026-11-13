# 第 14 章で打つコマンド (リポジトリの直下で流す。docker が使える端末が必要)
# 入力を作り、ETL のイメージをビルドして、MinIO (localhost:9000) に向けて流す
python examples/b14/make_input.py examples/b14/data/events.jsonl
docker build -t neboske-etl:dev examples/b14/etl
docker run --rm --network host -v "$PWD/examples/b14/data":/data:ro \
  -e S3_ENDPOINT=http://localhost:9000 -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin \
  -e BUCKET=lake-demo -e CREATE_BUCKET=1 neboske-etl:dev

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
