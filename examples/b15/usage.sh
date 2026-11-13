# リポジトリの直下で動かします。サービス (Redpanda) は docker compose up -d --wait で起動済みとします。
docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -e KAFKA_BOOTSTRAP=localhost:19092 -v "$PWD":/w -w /w de-book-dev python examples/b15/demo.py

# demo.py が表示したトピック名・グループ名を入れて、ブローカー側から様子を見ます (rpk は Redpanda の CLI です)。
docker compose exec redpanda rpk topic describe "$TOPIC" --print-partitions
docker compose exec redpanda rpk group describe "$GROUP"
docker compose exec redpanda rpk topic describe "$TOPIC" --print-configs
