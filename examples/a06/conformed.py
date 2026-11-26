"""適合ディメンションとバス行列: 複数のファクトが同じディメンションを共有する約束。"""
import models

DRILL_ACROSS = """
SELECT c.prefecture, s.revenue, e.purchases, round(s.revenue / e.purchases, 1) AS revenue_per_purchase_event
FROM (SELECT dc.prefecture, sum(f.amount) AS revenue
      FROM fact_sales f JOIN dim_customer dc USING (customer_key) GROUP BY ALL) s
JOIN (SELECT dc.prefecture, count(*) AS purchases
      FROM fact_events fe JOIN dim_customer dc USING (customer_key)
      WHERE fe.event_type = 'purchase' GROUP BY ALL) e USING (prefecture)
JOIN (SELECT DISTINCT prefecture FROM dim_customer) c USING (prefecture)
ORDER BY prefecture
"""


def build_events_fact(con):
    """行動ログのファクトを、売上と同じ dim_customer (適合ディメンション) に結び付けて作ります。"""
    con.execute("""CREATE TABLE fact_events AS
        SELECT e.event_id, dc.customer_key, e.event_type, CAST(e.event_time AS DATE) AS date_key
        FROM events e JOIN dim_customer dc ON dc.customer_id = e.customer_id""")


def non_conformed_demo():
    """別のチームが、同じ顧客を別の綴りの都道府県で持つと、2 つのファクトを都道府県で突き合わせられない。"""
    con = models.load_source(1)
    models.build_star(con)
    build_events_fact(con)
    con.execute("""CREATE TABLE dim_customer_team_b AS
        SELECT customer_key, CASE prefecture WHEN '東京' THEN '東京都' WHEN '大阪' THEN '大阪府'
               WHEN '京都' THEN '京都府' WHEN '北海道' THEN '北海道' ELSE prefecture || '県' END AS prefecture
        FROM dim_customer""")
    shared = con.execute(DRILL_ACROSS).fetchall()
    mismatched = con.execute("""
        SELECT count(*) FROM (SELECT DISTINCT prefecture FROM dim_customer) a
        JOIN (SELECT DISTINCT prefecture FROM dim_customer_team_b) b USING (prefecture)""").fetchone()[0]
    all_a = con.execute("SELECT count(DISTINCT prefecture) FROM dim_customer").fetchone()[0]
    return {"prefectures_matched_with_shared_dimension": len(shared), "prefectures": all_a,
            "prefectures_matched_with_team_b_spelling": mismatched}


def adding_a_column_breaks_select_star():
    """ディメンションに列を足すと、`SELECT *` で別の表へ複製していた下流の取り込みが壊れることを再現します。"""
    con = models.load_source(1)
    models.build_star(con)
    con.execute("CREATE TABLE downstream_customer AS SELECT * FROM dim_customer")
    con.execute("ALTER TABLE dim_customer ADD COLUMN tier VARCHAR")
    try:
        con.execute("INSERT INTO downstream_customer SELECT * FROM dim_customer")
        return None
    except Exception as exc:  # DuckDB の BinderException
        return str(exc).splitlines()[0]
