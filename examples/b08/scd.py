"""ゆっくり変わるディメンション（SCD）: タイプ 1（上書き）とタイプ 2（行を足す）。"""
from datetime import date

import duckdb

from star_schema import FACT_ORDER_ITEMS_SQL, FAR_FUTURE, build_star

# タイプ 1: 履歴を残さず上書きする。過去のファクトも新しい名前で見えるようになる。
SCD1_SQL = """
UPDATE dim_product SET name = '枕(標準・改良版)'
WHERE product_id = 1
"""

# タイプ 2 の手順 1: 今日の顧客マスタ（customers_today）と比べて、属性が変わった顧客を見つける。
FIND_CHANGES_SQL = """
CREATE OR REPLACE TEMP TABLE scd2_changes AS
SELECT t.customer_id, t.name, t.email, t.prefecture
FROM customers_today AS t
JOIN dim_customer AS c ON c.customer_id = t.customer_id AND c.is_current
WHERE c.name IS DISTINCT FROM t.name
   OR c.email IS DISTINCT FROM t.email
   OR c.prefecture IS DISTINCT FROM t.prefecture
"""

# 手順 2: 変わった顧客の現行の行を閉じる（valid_to を今日にして、現行フラグを下ろす）。
CLOSE_OLD_SQL = """
UPDATE dim_customer SET valid_to = ?, is_current = false
WHERE is_current AND customer_id IN (SELECT customer_id FROM scd2_changes)
"""

# 手順 3: 新しい版の行を足す。新しい代理キーが振られ、今日から有効になる。
OPEN_NEW_SQL = f"""
INSERT INTO dim_customer
SELECT nextval('customer_key_seq'), customer_id, name, email, prefecture, ?, DATE '{FAR_FUTURE}', true
FROM scd2_changes
"""

# 手順 4: まだディメンションに無い新規の顧客も足す。
ADD_NEW_CUSTOMERS_SQL = f"""
INSERT INTO dim_customer
SELECT nextval('customer_key_seq'), t.customer_id, t.name, t.email, t.prefecture, ?, DATE '{FAR_FUTURE}', true
FROM customers_today AS t
WHERE t.customer_id NOT IN (SELECT customer_id FROM dim_customer)
"""


def apply_scd2(con: duckdb.DuckDBPyConnection, as_of: date) -> int:
    """customers_today を取り込み、変更を履歴の行として残す。変更のあった顧客の数を返す。"""
    con.execute("BEGIN")
    con.execute(FIND_CHANGES_SQL)
    changed = con.execute("SELECT count(*) FROM scd2_changes").fetchone()[0]
    con.execute(CLOSE_OLD_SQL, [as_of])
    con.execute(OPEN_NEW_SQL, [as_of])
    con.execute(ADD_NEW_CUSTOMERS_SQL, [as_of])
    con.execute("COMMIT")
    return changed


# 引っ越しの例を作るため、as_of の前後どちらにも注文がある顧客を 3 人選ぶ。
PICK_MOVERS_SQL = """
SELECT customer_id FROM orders
GROUP BY customer_id
HAVING min(CAST(ordered_at AS TIMESTAMP)::DATE) < ? AND max(CAST(ordered_at AS TIMESTAMP)::DATE) >= ?
ORDER BY customer_id LIMIT 3
"""

MAKE_CUSTOMERS_TODAY_SQL = """
CREATE OR REPLACE TABLE customers_today AS
SELECT customer_id, name, email,
       CASE WHEN customer_id IN (SELECT unnest(?)) THEN
            CASE WHEN prefecture = '沖縄' THEN '北海道' ELSE '沖縄' END
            ELSE prefecture END AS prefecture
FROM customers
"""

# 同じ売上を、「注文した時点の都道府県」と「今の都道府県」で集計し直す。
AS_WAS_SQL = """
SELECT c.prefecture, sum(f.sales_amount)
FROM fact_order_items AS f JOIN dim_customer AS c USING (customer_key)
WHERE c.customer_id IN (SELECT unnest(?)) GROUP BY 1 ORDER BY 1
"""
AS_IS_SQL = """
SELECT cur.prefecture, sum(f.sales_amount)
FROM fact_order_items AS f
JOIN dim_customer AS c USING (customer_key)
JOIN dim_customer AS cur ON cur.customer_id = c.customer_id AND cur.is_current
WHERE c.customer_id IN (SELECT unnest(?)) GROUP BY 1 ORDER BY 1
"""


def run_scd2_demo(con: duckdb.DuckDBPyConnection, as_of: date = date(2026, 4, 1)) -> dict:
    """顧客 3 人が as_of に引っ越したとして、タイプ 2 で取り込み、ファクトを付け直して比べる。"""
    build_star(con)
    movers = [r[0] for r in con.execute(PICK_MOVERS_SQL, [as_of, as_of]).fetchall()]
    con.execute(MAKE_CUSTOMERS_TODAY_SQL, [movers])
    changed = apply_scd2(con, as_of)
    again = apply_scd2(con, as_of)  # 同じ入力をもう一度流しても、変更は 0 件（冪等）
    con.execute(FACT_ORDER_ITEMS_SQL)  # ファクトを、その時点の版にひもづけ直す
    return {
        "movers": movers, "changed": changed, "changed_again": again,
        "history": con.execute(
            "SELECT customer_id, prefecture, valid_from, valid_to, is_current FROM dim_customer"
            " WHERE customer_id = ? ORDER BY valid_from", [movers[0]]).fetchall(),
        "as_was": con.execute(AS_WAS_SQL, [movers]).fetchall(),
        "as_is": con.execute(AS_IS_SQL, [movers]).fetchall(),
    }


if __name__ == "__main__":
    con = duckdb.connect()
    out = run_scd2_demo(con)
    for key, value in out.items():
        print(key, value)
    con.execute(SCD1_SQL)
    print(con.execute("SELECT product_key, product_id, name FROM dim_product WHERE product_id = 1").fetchall())
