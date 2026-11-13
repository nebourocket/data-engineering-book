"""ゆっくり変わるディメンション（SCD）: タイプ 1（上書き）とタイプ 2（行を足す）。"""
from datetime import date

import duckdb

from star_schema import FACT_ORDER_ITEMS_SQL, build_star

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
OPEN_NEW_SQL = """
INSERT INTO dim_customer
SELECT nextval('customer_key_seq'), customer_id, name, email, prefecture, ?, DATE '9999-12-31', true
FROM scd2_changes
"""

# 手順 4: まだディメンションに無い新規の顧客も足す。
ADD_NEW_CUSTOMERS_SQL = """
INSERT INTO dim_customer
SELECT nextval('customer_key_seq'), t.customer_id, t.name, t.email, t.prefecture, ?, DATE '9999-12-31', true
FROM customers_today AS t
WHERE t.customer_id NOT IN (SELECT customer_id FROM dim_customer)
"""


# 取り込む前の確認: ソースの customer_id が NULL や重複だと、現行の行が 2 つできてしまう。
SOURCE_PROBLEMS_SQL = """
SELECT count(*) - count(customer_id) AS null_ids,
       count(customer_id) - count(DISTINCT customer_id) AS duplicate_ids
FROM customers_today
"""
# 変わる顧客の現行の行が、as_of と同じかそれより新しい valid_from を持つと、区間が空や逆転になる。
STALE_AS_OF_SQL = """
SELECT count(*) FROM dim_customer
WHERE is_current AND valid_from >= ? AND customer_id IN (SELECT customer_id FROM scd2_changes)
"""


def apply_scd2(con: duckdb.DuckDBPyConnection, as_of: date) -> int:
    """customers_today を取り込み、変更を履歴の行として残す。変更のあった顧客の数を返す。

    全体を 1 つのトランザクションにして、どこで失敗しても ROLLBACK する（行を閉じただけの状態を残さない）。
    """
    con.execute("BEGIN")
    try:
        null_ids, duplicate_ids = con.execute(SOURCE_PROBLEMS_SQL).fetchone()
        if null_ids or duplicate_ids:
            raise ValueError(f"customers_today に NULL の ID が {null_ids} 件、重複した ID が {duplicate_ids} 件あります")
        con.execute(FIND_CHANGES_SQL)
        if con.execute(STALE_AS_OF_SQL, [as_of]).fetchone()[0]:
            raise ValueError("as_of が、現在の版の valid_from より前（または同じ）です")
        changed = con.execute("SELECT count(*) FROM scd2_changes").fetchone()[0]
        con.execute(CLOSE_OLD_SQL, [as_of])
        con.execute(OPEN_NEW_SQL, [as_of])
        con.execute(ADD_NEW_CUSTOMERS_SQL, [as_of])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return changed


# 取り込んだあとの確認クエリ。どれも「0 行」が正常。
GAPS_OR_OVERLAPS_SQL = """
SELECT customer_id, valid_from, valid_to, next_from FROM (
    SELECT customer_id, valid_from, valid_to,
           lead(valid_from) OVER (PARTITION BY customer_id ORDER BY valid_from) AS next_from
    FROM dim_customer)
WHERE next_from IS NOT NULL AND next_from <> valid_to
"""
BAD_CURRENT_SQL = """
SELECT customer_id, count(*) FILTER (WHERE is_current) AS current_rows
FROM dim_customer GROUP BY customer_id
HAVING count(*) FILTER (WHERE is_current) <> 1
"""
# ソースから消えた顧客。この章の apply_scd2 は何もしない（消すか閉じるかは業務に聞いて決める）。
VANISHED_SQL = """
SELECT customer_id FROM dim_customer
WHERE is_current AND customer_id > 0
  AND customer_id NOT IN (SELECT customer_id FROM customers_today WHERE customer_id IS NOT NULL)
"""


def scd2_problems(con: duckdb.DuckDBPyConnection) -> dict[str, list]:
    return {name: con.execute(sql).fetchall() for name, sql in (
        ("gaps_or_overlaps", GAPS_OR_OVERLAPS_SQL), ("bad_current", BAD_CURRENT_SQL),
        ("vanished", VANISHED_SQL))}


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


# ファクトが、顧客のどの版（代理キー）にひもづいているか。
ORDERS_BY_VERSION_SQL = """
SELECT c.customer_key, c.prefecture, count(DISTINCT f.order_id) AS orders
FROM fact_order_items AS f JOIN dim_customer AS c USING (customer_key)
WHERE c.customer_id = ?
GROUP BY 1, 2 ORDER BY 1
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
        "orders_by_version": con.execute(ORDERS_BY_VERSION_SQL, [movers[0]]).fetchall(),
        "as_was": con.execute(AS_WAS_SQL, [movers]).fetchall(),
        "as_is": con.execute(AS_IS_SQL, [movers]).fetchall(),
    }


def history_rows(con: duckdb.DuckDBPyConnection, customer_id: int) -> list[tuple]:
    return con.execute(
        "SELECT customer_key, customer_id, prefecture, valid_from, valid_to, is_current"
        " FROM dim_customer WHERE customer_id = ? ORDER BY valid_from", [customer_id]).fetchall()


def write_history_csv(path) -> None:
    """本文の表（SCD2 の前後）を、実際の実行結果から CSV に書く。"""
    import csv

    con = duckdb.connect()
    build_star(con)
    movers = [r[0] for r in con.execute(PICK_MOVERS_SQL, [date(2026, 4, 1)] * 2).fetchall()]
    before = history_rows(con, movers[0])
    con.execute(MAKE_CUSTOMERS_TODAY_SQL, [movers])
    apply_scd2(con, date(2026, 4, 1))
    after = history_rows(con, movers[0])
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["時点", "customer_key", "customer_id", "prefecture", "valid_from", "valid_to", "is_current"])
        for label, rows in (("変更前", before), ("変更後", after)):
            for key, cid, pref, vf, vt, cur in rows:
                w.writerow([label, key, cid, pref, vf, vt, "真" if cur else "偽"])


if __name__ == "__main__":
    con = duckdb.connect()
    out = run_scd2_demo(con)
    for key, value in out.items():
        print(key, value)
    con.execute(SCD1_SQL)
    print(con.execute("SELECT product_key, product_id, name FROM dim_product WHERE product_id = 1").fetchall())
