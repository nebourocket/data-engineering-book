# 共有の PostgreSQL (wal_level=replica) で動く検査
docker run --rm --network host -e PG_DSN=postgresql://deb:deb@localhost:5432/deb \
  -v "$PWD":/w -w /w de-book-advanced pytest -q examples/a05

# 論理デコーディングの検査: 専用の PostgreSQL を一時的に起動する
docker run -d --rm --name a5-logical -p 55432:5432 -e POSTGRES_PASSWORD=x postgres:16 -c wal_level=logical
docker run --rm --network host \
  -e PG_DSN=postgresql://deb:deb@localhost:5432/deb \
  -e PG_LOGICAL_DSN=postgresql://postgres:x@localhost:55432/postgres \
  -v "$PWD":/w -w /w de-book-advanced python examples/a05/demo.py
docker stop a5-logical
