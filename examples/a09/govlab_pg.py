"""PostgreSQL に使い捨てのロールとスキーマを作る小さな道具です。"""
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import make_conninfo

from govlab_data import load_shop

ROLES = ["a09_analyst", "a09_support", "a09_etl", "a09_pii_reader", "a09_owner"]
PASSWORD = "pw"  # 使い捨ての検査用。本番では SSO や短命のトークンにします


class Box:
    def __init__(self, dsn):
        self.dsn = dsn

    def connect(self, role=None):
        """role の名前で本当にログインした接続を返します。role なしは管理者です。"""
        dsn = self.dsn if role is None else make_conninfo(self.dsn, user=role, password=PASSWORD)
        return psycopg.connect(dsn, autocommit=True)


def teardown(admin):
    admin.execute("DROP SCHEMA IF EXISTS a09 CASCADE")
    for role in ROLES:
        exists = admin.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role]).fetchone()
        if exists:
            admin.execute(f"DROP OWNED BY {role}")
            admin.execute(f"DROP ROLE {role}")


@contextmanager
def sandbox(dsn, setup_sql):
    """ロール 5 つとスキーマ a09 を作り、setup_sql を流し、顧客と注文を入れます。終わると全部消します。"""
    box = Box(dsn)
    with box.connect() as admin:
        teardown(admin)
        for role in ROLES:
            login = "LOGIN PASSWORD '" + PASSWORD + "'" if role != "a09_pii_reader" else "NOLOGIN"
            admin.execute(f"CREATE ROLE {role} {login}")
        admin.execute("GRANT a09_pii_reader TO a09_etl")
        admin.execute("CREATE SCHEMA a09 AUTHORIZATION a09_owner")
        customers, orders = load_shop()
        admin.execute("SET ROLE a09_owner")
        admin.execute(setup_sql["tables"])
        admin.execute("RESET ROLE")
        with admin.cursor() as cur:
            cur.executemany(
                "INSERT INTO a09.customers VALUES (%(customer_id)s, %(name)s, %(email)s, %(phone)s, "
                "%(prefecture)s, %(birth_year)s, %(registered_at)s)", customers)
            cur.executemany(
                "INSERT INTO a09.orders VALUES (%(order_id)s, %(customer_id)s, %(ordered_at)s, %(status)s, %(note)s)",
                orders)
        admin.execute("SET ROLE a09_owner")
        admin.execute(setup_sql["policies"])
        admin.execute("RESET ROLE")
        try:
            yield box
        finally:
            teardown(admin)
