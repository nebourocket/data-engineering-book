# 使い捨ての PostgreSQL を起動し、ロールを作れる接続 (PG_ADMIN_DSN) を渡して検査とデモを流す
# DE_BOOK_REQUIRE_SERVICES=1: PostgreSQL が無いときは skip ではなく fail にする (権限の検査を黙って飛ばさない)
set -euo pipefail
trap 'docker stop a9-pg 2>/dev/null || true; docker network rm a9net 2>/dev/null || true' EXIT
docker stop a9-pg 2>/dev/null || true        # 前回の残りがあれば片づける
docker network rm a9net 2>/dev/null || true
docker network create a9net
docker run -d --rm --name a9-pg --network a9net -e POSTGRES_PASSWORD=x postgres:16
until docker exec a9-pg pg_isready -U postgres; do sleep 1; done
docker run --rm --network a9net --user "$(id -u):$(id -g)" -v /etc/passwd:/etc/passwd:ro -e HOME=/tmp \
  -e PG_ADMIN_DSN=postgresql://postgres:x@a9-pg:5432/postgres -e DE_BOOK_REQUIRE_SERVICES=1 \
  -v "$PWD":/w -w /w de-book-advanced pytest -q examples/a09
docker run --rm --network a9net --user "$(id -u):$(id -g)" -v /etc/passwd:/etc/passwd:ro -e HOME=/tmp \
  -e PG_ADMIN_DSN=postgresql://postgres:x@a9-pg:5432/postgres -e DE_BOOK_REQUIRE_SERVICES=1 \
  -v "$PWD":/w -w /w de-book-advanced python examples/a09/demo.py
