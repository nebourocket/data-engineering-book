"""モデルの変更を、後方互換に進めます: 並べて作る → 突き合わせる → ビューを切り替える → 古い表を消す。"""
SALES_V1 = """CREATE TABLE fact_sales_v1 AS
SELECT order_id, line_no, quantity * unit_price AS amount FROM order_items"""
# v2: 値引き (discount) の列を足し、amount を line_amount に改名した新しい表
SALES_V2 = """CREATE TABLE fact_sales_v2 AS
SELECT order_id, line_no, quantity * unit_price AS line_amount,
       CASE WHEN quantity >= 3 THEN quantity * unit_price // 10 ELSE 0 END AS discount
FROM order_items"""
# 丸めを間違えた v2 (100 円未満を切り捨てている)
SALES_V2_BUGGY = SALES_V2.replace("quantity * unit_price AS line_amount", "quantity * unit_price // 100 * 100 AS line_amount")


def reconcile(con, old_sql, new_sql):
    """旧と新の出力を、行の単位で突き合わせます (片方にしかない行の数)。"""
    only_old = con.execute(f"SELECT count(*) FROM (({old_sql}) EXCEPT ({new_sql}))").fetchone()[0]
    only_new = con.execute(f"SELECT count(*) FROM (({new_sql}) EXCEPT ({old_sql}))").fetchone()[0]
    return {"only_in_old": only_old, "only_in_new": only_new}


def migrate(con, ddl_v2=SALES_V2):
    """新旧の突き合わせが 0 件なら、sales ビューを新しい表に向け替えます。"""
    con.execute(SALES_V1)
    con.execute("CREATE VIEW sales AS SELECT order_id, line_no, amount FROM fact_sales_v1")  # 利用者が見る窓口
    con.execute(ddl_v2)
    diff = reconcile(con, "SELECT order_id, line_no, amount FROM sales",
                     "SELECT order_id, line_no, line_amount AS amount FROM fact_sales_v2")
    switched = diff == {"only_in_old": 0, "only_in_new": 0}
    if switched:
        # 古い列名 amount を残したまま中身を向け替える。利用者の SQL は変わらない
        con.execute("CREATE OR REPLACE VIEW sales AS "
                    "SELECT order_id, line_no, line_amount AS amount, discount FROM fact_sales_v2")
    return {"diff": diff, "switched": switched}
