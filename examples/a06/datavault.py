"""Data Vault 2.0 (ハブ・リンク・サテライト) をねぼすけ商店で作ります (DuckDB)。

ハッシュキーは、業務キーを文字にして MD5 で縮めた値です。ほかの表を引かずに計算できるので、
ハブ・リンク・サテライトを別々の工程が、どの順番で読み込んでも結果が変わりません。
"""
import random
import re

HK = "md5(upper(trim(CAST({} AS VARCHAR))))"
HK2 = "md5(upper(trim(CAST({} AS VARCHAR))) || '||' || upper(trim(CAST({} AS VARCHAR))))"
# バイナリ版: 32 文字の文字列ではなく、16 バイトの BLOB で持つ
FLAVORS = {"varchar": lambda expr: expr, "binary": lambda expr: f"unhex({expr})"}

DDL = """
CREATE TABLE hub_customer (hk_customer VARCHAR PRIMARY KEY, customer_id INTEGER, load_dts TIMESTAMP, rec_src VARCHAR);
CREATE TABLE hub_product  (hk_product  VARCHAR PRIMARY KEY, product_id  INTEGER, load_dts TIMESTAMP, rec_src VARCHAR);
CREATE TABLE hub_order    (hk_order    VARCHAR PRIMARY KEY, order_id    INTEGER, load_dts TIMESTAMP, rec_src VARCHAR);
CREATE TABLE link_order_customer (hk_link VARCHAR PRIMARY KEY, hk_order VARCHAR, hk_customer VARCHAR, load_dts TIMESTAMP, rec_src VARCHAR);
CREATE TABLE link_order_line (hk_link VARCHAR PRIMARY KEY, hk_order VARCHAR, hk_product VARCHAR, line_no INTEGER, load_dts TIMESTAMP, rec_src VARCHAR);
CREATE TABLE sat_customer (hk_customer VARCHAR, load_dts TIMESTAMP, hashdiff VARCHAR, name VARCHAR, prefecture VARCHAR, PRIMARY KEY (hk_customer, load_dts));
CREATE TABLE sat_product  (hk_product VARCHAR, load_dts TIMESTAMP, hashdiff VARCHAR, product_name VARCHAR, category VARCHAR, PRIMARY KEY (hk_product, load_dts));
CREATE TABLE sat_order    (hk_order VARCHAR, load_dts TIMESTAMP, hashdiff VARCHAR, status VARCHAR, ordered_at VARCHAR, shipping_fee INTEGER, PRIMARY KEY (hk_order, load_dts));
CREATE TABLE sat_order_line (hk_link VARCHAR, load_dts TIMESTAMP, hashdiff VARCHAR, quantity INTEGER, unit_price INTEGER, PRIMARY KEY (hk_link, load_dts))
"""

# 読み込み 1 つ = (宛先の表, 元になる SELECT)。元の SELECT はステージング (customers など) だけを見ます。
def make_loads(flavor="varchar"):
    """ハブ・リンクの読み込みとサテライトの読み込みの定義を作ります。flavor は "varchar" か "binary" です。"""
    w = FLAVORS[flavor]
    hk = lambda col: w(HK.format(col))  # noqa: E731
    hk2 = lambda a, b: w(HK2.format(a, b))  # noqa: E731
    hub_link = {
        # 注文の側にしか現れない顧客 (顧客の行が遅れて届く場合) もハブに入れるため、orders からも読む
        "hub_customer": f"SELECT {hk('customer_id')} AS hk_customer, customer_id FROM "
                        "(SELECT customer_id FROM customers UNION SELECT customer_id FROM orders)",
        "hub_product": f"SELECT {hk('product_id')} AS hk_product, product_id FROM base_products",
        "hub_order": f"SELECT {hk('order_id')} AS hk_order, order_id FROM orders",
        "link_order_customer": f"SELECT {hk2('order_id', 'customer_id')} AS hk_link, "
                               f"{hk('order_id')} AS hk_order, {hk('customer_id')} AS hk_customer FROM orders",
        "link_order_line": f"SELECT {hk2('order_id', 'line_no')} AS hk_link, {hk('order_id')} AS hk_order, "
                           f"{hk('product_id')} AS hk_product, line_no FROM order_items",
    }
    sat = {
        # 表名: (キー列, 元の SELECT (キー列と hashdiff 以外の列を持つ), 属性列)
        "sat_customer": ("hk_customer", f"SELECT {hk('customer_id')} AS hk_customer, name, prefecture FROM customers",
                         ["name", "prefecture"]),
        "sat_product": ("hk_product", f"SELECT {hk('product_id')} AS hk_product, name AS product_name, category FROM base_products",
                        ["product_name", "category"]),
        "sat_order": ("hk_order", f"SELECT {hk('order_id')} AS hk_order, status, ordered_at, shipping_fee FROM orders",
                      ["status", "ordered_at", "shipping_fee"]),
        "sat_order_line": ("hk_link", f"SELECT {hk2('order_id', 'line_no')} AS hk_link, quantity, unit_price FROM order_items",
                           ["quantity", "unit_price"]),
    }
    return hub_link, sat


HUB_LINK_LOADS, SAT_LOADS = make_loads("varchar")


def create_vault(con, flavor="varchar"):
    """表を作ります。binary のときは、ハッシュキーと hashdiff の列を BLOB にします。"""
    ddl = DDL if flavor == "varchar" else re.sub(r"(hk_\w+|hashdiff) VARCHAR", r"\1 BLOB", DDL)
    con.execute(ddl)


def load_hub_or_link(con, table, load_dts="2026-06-30 00:00:00", flavor="varchar"):
    """ハブ・リンク: まだ無いキーだけ足します (何度流しても同じ結果)。"""
    key = con.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' "
                      "ORDER BY ordinal_position LIMIT 1").fetchone()[0]
    cols = [r[0] for r in con.execute(f"SELECT column_name FROM information_schema.columns "
                                      f"WHERE table_name = '{table}' ORDER BY ordinal_position").fetchall()]
    business = [c for c in cols if c not in ("load_dts", "rec_src")]
    con.execute(f"""
        INSERT INTO {table} ({', '.join(business)}, load_dts, rec_src)
        SELECT DISTINCT {', '.join('s.' + c for c in business)}, TIMESTAMP '{load_dts}', 'shop'
        FROM ({make_loads(flavor)[0][table]}) s
        WHERE NOT EXISTS (SELECT 1 FROM {table} t WHERE t.{key} = s.{key})""")


def load_satellite(con, table, load_dts, flavor="varchar"):
    """サテライト: 最新の行と hashdiff (属性をまとめた MD5) が違うときだけ、新しい行を足します。"""
    key, source, attrs = make_loads(flavor)[1][table]
    hashdiff = FLAVORS[flavor]("md5(" + " || '||' || ".join(f"coalesce(CAST({a} AS VARCHAR), '')" for a in attrs) + ")")
    con.execute(f"""
        INSERT INTO {table}
        SELECT s.{key}, TIMESTAMP '{load_dts}', s.hashdiff, {', '.join('s.' + a for a in attrs)}
        FROM (SELECT *, {hashdiff} AS hashdiff FROM ({source})) s
        LEFT JOIN (SELECT {key}, hashdiff FROM {table}
                   QUALIFY row_number() OVER (PARTITION BY {key} ORDER BY load_dts DESC) = 1) cur USING ({key})
        WHERE cur.hashdiff IS DISTINCT FROM s.hashdiff""")


def load_all(con, order=None, seed=None, load_dts="2026-06-30 00:00:00", flavor="varchar"):
    """全部の読み込みを実行します。seed を渡すと順番をその乱数で入れ替えます (結果は変わらないはずです)。"""
    steps = [("hub", t) for t in HUB_LINK_LOADS] + [("sat", t) for t in SAT_LOADS]
    if seed is not None:
        random.Random(seed).shuffle(steps)
    for kind, table in steps:
        if kind == "hub":
            load_hub_or_link(con, table, load_dts, flavor)
        else:
            load_satellite(con, table, load_dts, flavor)
    return [t for _, t in steps]


def digest(con, tables):
    """表の中身を順序に依存せずに要約した値 (行数と MD5) を返します。load_dts は除きます。"""
    out = {}
    for t in tables:
        cols = [r[0] for r in con.execute(f"SELECT column_name FROM information_schema.columns "
                                          f"WHERE table_name = '{t}' AND column_name <> 'load_dts' "
                                          "ORDER BY ordinal_position").fetchall()]
        row = " || '|' || ".join(f"coalesce(CAST({c} AS VARCHAR), '')" for c in cols)
        out[t] = con.execute(f"SELECT count(*), md5(string_agg({row}, ',' ORDER BY {row})) FROM {t}").fetchone()
    return out


CURRENT_VIEWS = """
CREATE VIEW cur_sat_customer AS SELECT * FROM sat_customer QUALIFY row_number() OVER (PARTITION BY hk_customer ORDER BY load_dts DESC) = 1;
CREATE VIEW cur_sat_product AS SELECT * FROM sat_product QUALIFY row_number() OVER (PARTITION BY hk_product ORDER BY load_dts DESC) = 1;
CREATE VIEW cur_sat_order AS SELECT * FROM sat_order QUALIFY row_number() OVER (PARTITION BY hk_order ORDER BY load_dts DESC) = 1;
CREATE VIEW cur_sat_order_line AS SELECT * FROM sat_order_line QUALIFY row_number() OVER (PARTITION BY hk_link ORDER BY load_dts DESC) = 1;
CREATE VIEW v_sales AS
SELECT ho.order_id, ll.line_no, so.status, so.ordered_at, so.shipping_fee, hc.customer_id,
       coalesce(sc.name, '(未着)') AS customer_name, coalesce(sc.prefecture, '(未着)') AS prefecture,
       sp.product_name, sp.category, sl.quantity, sl.quantity * sl.unit_price AS amount
FROM hub_order ho
JOIN cur_sat_order so USING (hk_order)
JOIN link_order_customer lc USING (hk_order)
JOIN hub_customer hc USING (hk_customer)
LEFT JOIN cur_sat_customer sc USING (hk_customer)
JOIN link_order_line ll USING (hk_order)
JOIN cur_sat_order_line sl ON sl.hk_link = ll.hk_link
JOIN cur_sat_product sp USING (hk_product)
"""
REVENUE_VAULT = """
SELECT substr(ordered_at, 1, 7) AS month, prefecture, category, sum(amount) AS revenue
FROM v_sales WHERE status <> 'cancelled'
GROUP BY ALL ORDER BY ALL
"""


PIT_SQL = """
CREATE OR REPLACE TABLE pit_line AS
SELECT ll.hk_link, ll.hk_order, ll.hk_product, lc.hk_customer,
       (SELECT max(load_dts) FROM sat_order so WHERE so.hk_order = ll.hk_order) AS so_dts,
       (SELECT max(load_dts) FROM sat_customer sc WHERE sc.hk_customer = lc.hk_customer) AS sc_dts,
       (SELECT max(load_dts) FROM sat_order_line sl WHERE sl.hk_link = ll.hk_link) AS sl_dts,
       (SELECT max(load_dts) FROM sat_product sp WHERE sp.hk_product = ll.hk_product) AS sp_dts
FROM link_order_line ll JOIN link_order_customer lc USING (hk_order)
"""
REVENUE_PIT = """
SELECT substr(so.ordered_at, 1, 7) AS month, coalesce(sc.prefecture, '(未着)') AS prefecture, sp.category, sum(sl.quantity * sl.unit_price) AS revenue
FROM pit_line p
JOIN sat_order so ON so.hk_order = p.hk_order AND so.load_dts = p.so_dts
LEFT JOIN sat_customer sc ON sc.hk_customer = p.hk_customer AND sc.load_dts = p.sc_dts
JOIN sat_order_line sl ON sl.hk_link = p.hk_link AND sl.load_dts = p.sl_dts
JOIN sat_product sp ON sp.hk_product = p.hk_product AND sp.load_dts = p.sp_dts
WHERE so.status <> 'cancelled'
GROUP BY ALL ORDER BY ALL
"""


def hash_collision_example(con):
    """区切り文字 '||' が業務キーの中に入ると、別のキーの組が同じハッシュになることを示します。"""
    expr = HK2.format("'{}'", "'{}'")
    a = con.execute("SELECT " + expr.format("A||B", "C")).fetchone()[0]
    b = con.execute("SELECT " + expr.format("A", "B||C")).fetchone()[0]
    return a == b
