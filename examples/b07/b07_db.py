"""第7章の共通部品: PostgreSQL への接続と、スキーマ b07 の作り直し。"""
import psycopg


def connect(dsn: str) -> psycopg.Connection:
    """スキーマ b07 を既定にして接続します。autocommit にして BEGIN / COMMIT を自分で書きます。"""
    return psycopg.connect(dsn, autocommit=True, options="-c search_path=b07")


def reset_schema(dsn: str) -> None:
    """スキーマ b07 を消して作り直します（章のコード例だけが使う場所です）。"""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS b07 CASCADE")
        conn.execute("CREATE SCHEMA b07")
