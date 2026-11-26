"""第16章: ウェアハウスの結果を、営業の顧客管理 (CRM) に見立てた SQLite へ書き戻します。"""
import sqlite3

import duckdb

# CRM 側の表。owner は営業担当が CRM の画面で入力する列で、同期は触りません。
CONTACTS_DDL = """
create table if not exists contacts (
    customer_id integer primary key,
    email text not null,
    segment text not null,
    lifetime_spend integer not null,
    changed_at text not null,
    owner text
)
"""

SOURCE_SQL = """
select customer_id, email, segment, lifetime_spend
from customer_summary
where email is not null
order by customer_id
"""

SKIPPED_SQL = "select count(*) from customer_summary where email is null"

UPSERT_SQL = """
insert into contacts (customer_id, email, segment, lifetime_spend, changed_at)
values (?, ?, ?, ?, ?)
on conflict (customer_id) do update set
    email = excluded.email,
    segment = excluded.segment,
    lifetime_spend = excluded.lifetime_spend,
    changed_at = excluded.changed_at
where contacts.email is not excluded.email
   or contacts.segment is not excluded.segment
   or contacts.lifetime_spend is not excluded.lifetime_spend
"""

# 比べるための悪い書き方 2 つ。
REPLACE_SQL = """
insert or replace into contacts (customer_id, email, segment, lifetime_spend, changed_at)
values (?, ?, ?, ?, ?)
"""

NAIVE_DDL = """
create table if not exists contacts_naive (
    customer_id integer,
    email text,
    segment text,
    lifetime_spend integer,
    changed_at text
)
"""

NAIVE_INSERT_SQL = """
insert into contacts_naive (customer_id, email, segment, lifetime_spend, changed_at)
values (?, ?, ?, ?, ?)
"""


def read_source(warehouse: duckdb.DuckDBPyConnection) -> tuple[list[tuple], int]:
    """送る行と、メールが無くて送れない顧客の数を返します。"""
    rows = warehouse.execute(SOURCE_SQL).fetchall()
    skipped = warehouse.execute(SKIPPED_SQL).fetchone()[0]
    return rows, skipped


def apply_upsert(crm: sqlite3.Connection, rows: list[tuple], changed_at: str) -> dict:
    """全行を 1 つのトランザクションで書き込み、新規・更新・変化なしの件数を返します。"""
    crm.execute(CONTACTS_DDL)
    count_before = crm.execute("select count(*) from contacts").fetchone()[0]
    changes_before = crm.total_changes
    with crm:  # 途中で失敗したら全部取り消します
        crm.executemany(UPSERT_SQL, [(*row, changed_at) for row in rows])
    count_after = crm.execute("select count(*) from contacts").fetchone()[0]
    changes = crm.total_changes - changes_before
    inserted = count_after - count_before
    return {
        "read": len(rows),
        "inserted": inserted,
        "updated": changes - inserted,
        "unchanged": len(rows) - changes,
    }


def sync_contacts(warehouse: duckdb.DuckDBPyConnection, crm: sqlite3.Connection, changed_at: str) -> dict:
    rows, skipped = read_source(warehouse)
    result = apply_upsert(crm, rows, changed_at)
    result["skipped"] = skipped
    return result
