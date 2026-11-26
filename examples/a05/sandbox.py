"""PostgreSQL に使い捨てのスキーマを作る小さな道具です (テストと demo.py が使います)。"""
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg


@dataclass
class Box:
    dsn: str
    schema: str

    def connect(self, **kwargs):
        """このスキーマだけを search_path に持つ接続を返します。"""
        return psycopg.connect(self.dsn, options=f"-c search_path={self.schema}", **kwargs)


@contextmanager
def sandbox(dsn, name=None):
    schema = name or "a05_" + uuid.uuid4().hex[:8]
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
        try:
            yield Box(dsn, schema)
        finally:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")
