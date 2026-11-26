"""PII の探索: 列の中身を正規表現で調べ、名前に PII と書いていない列の漏れを見つけます。"""
import duckdb

from govlab_data import PREFECTURES_BY_REGION
from govlab_pseudo import keyed_hash

PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"0\d{1,4}-\d{1,4}-\d{4}",
}


def build(customers, orders):
    """顧客と注文を DuckDB に入れます (表 customers / orders)。"""
    con = duckdb.connect()
    con.execute("CREATE TABLE customers (customer_id INTEGER, name VARCHAR, email VARCHAR, phone VARCHAR, "
                "prefecture VARCHAR, birth_year INTEGER, registered_at VARCHAR)")
    con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)", [
        (c["customer_id"], c["name"], c["email"], c["phone"], c["prefecture"], c["birth_year"], c["registered_at"])
        for c in customers])
    con.execute("CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, ordered_at VARCHAR, status VARCHAR, note VARCHAR)")
    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", [
        (o["order_id"], o["customer_id"], o["ordered_at"], o["status"], o["note"]) for o in orders])
    return con


def scan(con, tables):
    """tables の文字列の列を全部調べ、パターンに当たった行数を {(表, 列, 種類): 行数} で返します。"""
    columns = con.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE data_type = 'VARCHAR' AND table_name IN (SELECT unnest(?)) "
        "ORDER BY table_name, ordinal_position", [list(tables)]).fetchall()
    hits = {}
    for table, column in columns:
        for kind, pattern in PATTERNS.items():
            n = con.execute(
                f'SELECT count(*) FROM {table} WHERE regexp_matches("{column}", ?)', [pattern]).fetchone()[0]
            if n:
                hits[(table, column, kind)] = n
    return hits


def dev_copy(con, key):
    """開発用の複製。氏名・メール・電話・顧客番号は仮名化 (HMAC)、都道府県は地方、生年は十年単位、
    登録日は月に丸め、メモは PII を伏せ字にします。顧客番号を仮名化するのは、注文と結べる番号が残ると
    本番の顧客と突き合わせられるからです (注文側の番号も同じ鍵で仮名化します)。"""
    con.execute("CREATE OR REPLACE TABLE dev_customers (customer_id VARCHAR, name VARCHAR, email VARCHAR, "
                "phone VARCHAR, region VARCHAR, birth_decade INTEGER, reg_month VARCHAR)")
    rows = con.execute("SELECT customer_id, name, email, phone, prefecture, birth_year, registered_at "
                       "FROM customers").fetchall()
    hashed = lambda v: None if v is None else keyed_hash(str(v), key)  # noqa: E731
    con.executemany("INSERT INTO dev_customers VALUES (?, ?, ?, ?, ?, ?, ?)", [
        (hashed(cid), hashed(name), hashed(email), hashed(phone), PREFECTURES_BY_REGION[pref],
         year // 10 * 10, reg[:7])
        for cid, name, email, phone, pref, year, reg in rows])
    scrubbed = "note"
    for pattern in PATTERNS.values():
        scrubbed = f"regexp_replace({scrubbed}, '{pattern}', '[伏せ字]', 'g')"
    orders = con.execute(f"SELECT order_id, customer_id, ordered_at, status, {scrubbed} FROM orders").fetchall()
    con.execute("CREATE OR REPLACE TABLE dev_orders (order_id INTEGER, customer_id VARCHAR, ordered_at VARCHAR, "
                "status VARCHAR, note VARCHAR)")
    con.executemany("INSERT INTO dev_orders VALUES (?, ?, ?, ?, ?)", [
        (oid, hashed(cid), at, status, note) for oid, cid, at, status, note in orders])
