"""ケーススタディ: 開発用に本番の複製を渡す前に、PII を探し、仮名化し、破られないかを確かめます。"""
from govlab_data import load_shop
from govlab_pseudo import dictionary_attack, keyed_hash, plain_hash, small_groups
from govlab_scan import build, dev_copy, scan

SECRET = b"demo-secret-key-do-not-use"  # 実際の鍵はコードに書かず、鍵管理サービスや環境変数から読みます


def run():
    customers, orders = load_shop()
    con = build(customers, orders)
    before = scan(con, ["customers", "orders"])

    emails = [c["email"] for c in customers if c["email"]]
    naive = dictionary_attack([plain_hash(e) for e in emails], plain_hash)
    dev_copy(con, SECRET)
    dev_emails = [r[0] for r in con.execute("SELECT email FROM dev_customers WHERE email IS NOT NULL").fetchall()]
    after_attack = dictionary_attack(dev_emails, plain_hash)
    with_key = dictionary_attack([keyed_hash(e, SECRET) for e in emails], lambda v: keyed_hash(v, SECRET))
    after = scan(con, ["dev_customers", "dev_orders"])
    k_dev_month = small_groups(con, "dev_customers", ["region", "birth_decade", "reg_month"])
    con.execute("ALTER TABLE dev_customers DROP COLUMN reg_month")  # 月でも粗くない: 登録日は複製から落とす

    return {
        "scan_before": before, "scan_after": after, "emails": len(emails),
        "naive_recovered": naive, "hmac_recovered": after_attack, "insider_with_key": with_key,
        "k_pref_year": small_groups(con, "customers", ["prefecture", "birth_year"]),
        "k_raw": small_groups(con, "customers", ["prefecture", "birth_year", "registered_at"]),
        "k_dev_month": k_dev_month,
        "k_dev": small_groups(con, "dev_customers", ["region", "birth_decade"]),
        "dev_key_shared": con.execute("SELECT count(*) FROM dev_orders o JOIN dev_customers c USING (customer_id)").fetchone()[0],
        "orders": len(orders),
    }
