"""遅れて届くディメンション: 明細が先に届き、顧客の行が後から来る場合の扱い。"""
import models

UNKNOWN = "(未着)"


def build(con, late_mod=20):
    """customer_id が late_mod の倍数の顧客を、ディメンションにまだ入れない状態を作ります。"""
    con.execute(f"""CREATE TABLE dim_customer AS
        SELECT row_number() OVER (ORDER BY customer_id) AS customer_key, customer_id, name, prefecture,
               false AS is_inferred
        FROM customers WHERE customer_id % {late_mod} <> 0""")
    con.execute("""CREATE TABLE lines AS
        SELECT i.order_id, i.line_no, o.customer_id, i.quantity * i.unit_price AS amount
        FROM order_items i JOIN orders o USING (order_id)""")


def counts(con):
    """内部結合と外部結合で、見える明細と売上がどう違うかを数えます。"""
    total = con.execute("SELECT count(*), sum(amount) FROM lines").fetchone()
    inner = con.execute("SELECT count(*), sum(amount) FROM lines JOIN dim_customer USING (customer_id)").fetchone()
    return {"lines": total[0], "revenue": total[1], "inner_join_lines": inner[0], "inner_join_revenue": inner[1]}


def add_inferred_members(con):
    """届いていない顧客に、仮の行 (推定メンバー) を作ります。キーはここで確定し、あとで変わりません。"""
    return con.execute(f"""INSERT INTO dim_customer
        SELECT (SELECT max(customer_key) FROM dim_customer) + row_number() OVER (ORDER BY customer_id),
               customer_id, '{UNKNOWN}', '{UNKNOWN}', true
        FROM (SELECT DISTINCT customer_id FROM lines) l
        WHERE NOT EXISTS (SELECT 1 FROM dim_customer d WHERE d.customer_id = l.customer_id)""").fetchone()[0]


def late_arrival(con):
    """遅れていた顧客の行が届いたので、仮の行を本物の属性で埋めます (customer_key は同じまま)。"""
    return con.execute("""UPDATE dim_customer SET name = c.name, prefecture = c.prefecture, is_inferred = false
        FROM customers c WHERE c.customer_id = dim_customer.customer_id AND dim_customer.is_inferred""").fetchone()[0]


def revenue_unknown(con):
    return con.execute(f"SELECT count(*), coalesce(sum(amount), 0) FROM lines JOIN dim_customer USING (customer_id) "
                       f"WHERE prefecture = '{UNKNOWN}'").fetchone()


def demo():
    con = models.load_source(1)
    build(con)
    out = {"before_fix": counts(con)}
    out["inferred_members_added"] = add_inferred_members(con)
    out["after_inferred"] = {**counts(con), "unknown_lines_and_revenue": revenue_unknown(con)}
    out["rows_filled_on_arrival"] = late_arrival(con)
    out["after_arrival"] = {**counts(con), "unknown_lines_and_revenue": revenue_unknown(con)}
    return out


def vault_demo(late_mod=20):
    """Data Vault では同じ状況がどうなるか: 顧客の行 (サテライトの元) だけが遅れ、注文は先に届く。"""
    import datavault

    con = models.load_source(1)
    con.execute("CREATE TABLE customers_all AS SELECT * FROM customers")
    con.execute(f"DELETE FROM customers WHERE customer_id % {late_mod} = 0")
    datavault.create_vault(con)
    datavault.load_all(con)
    con.execute(datavault.CURRENT_VIEWS)

    def stats():
        return {"lines": con.execute("SELECT count(*) FROM v_sales").fetchone()[0],
                "unknown_lines": con.execute(f"SELECT count(*) FROM v_sales WHERE prefecture = '{UNKNOWN}'").fetchone()[0],
                "hub_customer": con.execute("SELECT count(*) FROM hub_customer").fetchone()[0],
                "sat_customer": con.execute("SELECT count(*) FROM sat_customer").fetchone()[0]}

    before = stats()
    con.execute(f"INSERT INTO customers SELECT * FROM customers_all WHERE customer_id % {late_mod} = 0")
    datavault.load_all(con, load_dts="2026-07-01 00:00:00")
    return {"before_arrival": before, "after_arrival": stats()}
