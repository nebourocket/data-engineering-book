"""第5章のフィクスチャ。

論理デコーディングは wal_level=logical の PostgreSQL が要ります。共有の PostgreSQL は
wal_level=replica なので、専用に起動したものを PG_LOGICAL_DSN で教えます (無ければ skip)。
  docker run -d --rm --name a5-logical -p 55432:5432 -e POSTGRES_PASSWORD=x \
      postgres:16 -c wal_level=logical
  export PG_LOGICAL_DSN=postgresql://postgres:x@localhost:55432/postgres
"""
import os
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))


@pytest.fixture
def logical_dsn():
    dsn = os.environ.get("PG_LOGICAL_DSN")
    if not dsn:
        pytest.skip("PG_LOGICAL_DSN が未設定です (wal_level=logical の PostgreSQL が要ります)")
    with psycopg.connect(dsn) as conn:
        level = conn.execute("SHOW wal_level").fetchone()[0]
    if level != "logical":
        pytest.skip(f"wal_level が {level} です (logical が要ります)")
    return dsn
