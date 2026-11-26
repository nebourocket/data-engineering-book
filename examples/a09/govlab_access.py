"""最小権限・行レベルセキュリティ・マスキングビュー・監査ログを PostgreSQL で組みます。"""
import psycopg

TABLES_SQL = """
CREATE TABLE a09.customers (customer_id int PRIMARY KEY, name text, email text, phone text,
                            prefecture text, birth_year int, registered_at text);
CREATE TABLE a09.orders (order_id int PRIMARY KEY, customer_id int, ordered_at text, status text, note text);
CREATE TABLE a09.staff_regions (staff text, prefecture text);
CREATE TABLE a09.audit_log (at timestamptz DEFAULT clock_timestamp(), actor text, op text, customer_id int, detail text);
"""

POLICIES_SQL = r"""
-- 1. 列ごとの権限: 分析者は PII の列を読めない
GRANT USAGE ON SCHEMA a09 TO a09_analyst, a09_support, a09_etl;
GRANT SELECT (customer_id, prefecture, birth_year, registered_at) ON a09.customers TO a09_analyst;
GRANT SELECT (order_id, customer_id, ordered_at, status) ON a09.orders TO a09_analyst;
GRANT SELECT (customer_id, name, prefecture, registered_at) ON a09.customers TO a09_support;
GRANT SELECT, DELETE, UPDATE (email, phone) ON a09.customers TO a09_etl;
GRANT SELECT ON a09.staff_regions TO a09_support;

-- 2. 行レベルセキュリティ: サポートは担当の都道府県の行だけ
ALTER TABLE a09.customers ENABLE ROW LEVEL SECURITY;
CREATE POLICY support_by_region ON a09.customers FOR SELECT TO a09_support
  USING (prefecture IN (SELECT prefecture FROM a09.staff_regions WHERE staff = current_user));
CREATE POLICY open_to_others ON a09.customers FOR ALL TO a09_analyst, a09_etl USING (true);

-- 3. マスキングビュー: PII を読める役割 (a09_pii_reader のメンバー) だけ生の値が見える
CREATE VIEW a09.customers_masked AS
SELECT customer_id, prefecture, birth_year,
       CASE WHEN pg_has_role(current_user, 'a09_pii_reader', 'member') THEN email
            ELSE regexp_replace(email, '^(.)[^@]*', '\1***') END AS email,
       CASE WHEN pg_has_role(current_user, 'a09_pii_reader', 'member') THEN phone
            ELSE '***-****-' || right(phone, 4) END AS phone
FROM a09.customers;
GRANT SELECT ON a09.customers_masked TO a09_analyst, a09_etl;

-- 4. ビューは作った人の権限で動く: 行レベルセキュリティをすり抜ける版と、防ぐ版 (security_invoker)
CREATE VIEW a09.customers_leaky AS SELECT customer_id, prefecture FROM a09.customers;
CREATE VIEW a09.customers_by_region WITH (security_invoker = true) AS SELECT customer_id, prefecture FROM a09.customers;
GRANT SELECT ON a09.customers_leaky, a09.customers_by_region TO a09_support;

-- 5. 監査: 変更はトリガで、PII の参照は専用の関数だけで記録する (値そのものはログに書かない)
CREATE FUNCTION a09.log_change() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = a09, pg_temp AS $$
BEGIN
  INSERT INTO a09.audit_log (actor, op, customer_id, detail)
  VALUES (session_user, TG_OP, OLD.customer_id,
          CASE WHEN TG_OP = 'UPDATE' THEN concat_ws(',',
               CASE WHEN NEW.email IS DISTINCT FROM OLD.email THEN 'email' END,
               CASE WHEN NEW.phone IS DISTINCT FROM OLD.phone THEN 'phone' END) END);
  RETURN NULL;
END $$;
CREATE TRIGGER customers_audit AFTER UPDATE OR DELETE ON a09.customers
  FOR EACH ROW EXECUTE FUNCTION a09.log_change();

CREATE FUNCTION a09.lookup_customer(p_id int, p_reason text)
RETURNS TABLE (name text, email text, phone text) LANGUAGE plpgsql SECURITY DEFINER
SET search_path = a09, pg_temp AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM a09.customers c JOIN a09.staff_regions s ON s.prefecture = c.prefecture
                 WHERE c.customer_id = p_id AND s.staff = session_user) THEN
    INSERT INTO a09.audit_log (actor, op, customer_id, detail) VALUES (session_user, 'READ_DENIED', p_id, p_reason);
    RETURN;
  END IF;
  INSERT INTO a09.audit_log (actor, op, customer_id, detail) VALUES (session_user, 'READ', p_id, p_reason);
  RETURN QUERY SELECT c.name, c.email, c.phone FROM a09.customers c WHERE c.customer_id = p_id;
END $$;
REVOKE ALL ON FUNCTION a09.lookup_customer(int, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION a09.lookup_customer(int, text) TO a09_support;

INSERT INTO a09.staff_regions VALUES ('a09_support', '東京'), ('a09_support', '神奈川');
"""

SETUP = {"tables": TABLES_SQL, "policies": POLICIES_SQL}


def attempt(box, role, sql, params=None):
    """role でログインして sql を流します。成功なら ('ok', 行), 失敗なら ('error', 1 行目のメッセージ)。"""
    with box.connect(role) as conn:
        try:
            return "ok", conn.execute(sql, params).fetchall()
        except psycopg.Error as e:
            return "error", str(e).splitlines()[0]


def access_matrix(box):
    """役割ごとに、同じ顧客表へ何ができて何ができないかを一覧にします。"""
    tries = [
        ("a09_analyst", "SELECT customer_id, prefecture FROM a09.customers"),
        ("a09_analyst", "SELECT customer_id, email FROM a09.customers"),
        ("a09_analyst", "SELECT * FROM a09.customers"),
        ("a09_analyst", "SELECT email, phone FROM a09.customers_masked WHERE customer_id = 1"),
        ("a09_etl", "SELECT email, phone FROM a09.customers_masked WHERE customer_id = 1"),
        ("a09_analyst", "SELECT note FROM a09.orders"),
    ]
    out = []
    for role, sql in tries:
        status, result = attempt(box, role, sql)
        out.append((role, sql, status, f"{len(result)} 行" if status == "ok" and len(result) > 1 else result))
    return out


def row_level(box):
    """行レベルセキュリティ: 同じ SELECT count(*) が、ログインした人によって変わる様子。"""
    count = "SELECT count(*) FROM a09.{}"
    return {
        "owner": attempt(box, "a09_owner", count.format("customers"))[1][0][0],
        "analyst": attempt(box, "a09_analyst", count.format("customers"))[1][0][0],
        "support": attempt(box, "a09_support", count.format("customers"))[1][0][0],
        "support_leaky_view": attempt(box, "a09_support", count.format("customers_leaky"))[1][0][0],
        "support_invoker_view": attempt(box, "a09_support", count.format("customers_by_region"))[1][0][0],
    }


def audit_demo(box):
    """更新・削除・PII の参照を実行して、監査ログを (誰が, 何を, 何件) に集計して返します。"""
    attempt(box, "a09_etl", "UPDATE a09.customers SET phone = '000-0000-0000' WHERE customer_id <= 3")
    attempt(box, "a09_etl", "DELETE FROM a09.customers WHERE customer_id = 500")
    attempt(box, "a09_support", "SELECT * FROM a09.lookup_customer(%s, %s)", [5, "問い合わせ #1234"])
    attempt(box, "a09_support", "SELECT * FROM a09.lookup_customer(%s, %s)", [8, "問い合わせ #1235"])
    attempt(box, "a09_support", "SELECT * FROM a09.lookup_customer(%s, %s)", [1, "好奇心"])
    tamper = attempt(box, "a09_etl", "DELETE FROM a09.audit_log")
    with box.connect() as admin:
        summary = admin.execute(
            "SELECT actor, op, count(*) FROM a09.audit_log GROUP BY actor, op ORDER BY actor, op").fetchall()
        reads = admin.execute(
            "SELECT customer_id, op, detail FROM a09.audit_log WHERE op LIKE 'READ%' ORDER BY at").fetchall()
    return {"summary": summary, "reads": reads, "tamper": tamper}


def read_bypass(box):
    """監査をすり抜ける読み方: a09_etl が表を直接読むと、READ の記録は増えません。(前, 後) の READ 行数。"""
    def reads(admin):
        return admin.execute("SELECT count(*) FROM a09.audit_log WHERE customer_id = 8 AND op = 'READ'").fetchone()[0]

    with box.connect() as admin:
        before = reads(admin)
        attempt(box, "a09_etl", "SELECT email, phone FROM a09.customers WHERE customer_id = 8")
        return before, reads(admin)


def who_touched(box, customer_id):
    """監査ログから「この顧客に、誰が、何をしたか」を時刻順に引きます。"""
    with box.connect() as admin:
        return admin.execute(
            "SELECT actor, op, detail FROM a09.audit_log WHERE customer_id = %s ORDER BY at", [customer_id]).fetchall()


def rls_exceptions(box):
    """行レベルセキュリティが効かない例: FORCE を付けた持ち主 / スーパーユーザー / BYPASSRLS を持つロール。"""
    count = "SELECT count(*) FROM a09.customers"
    with box.connect() as admin:
        admin.execute("ALTER TABLE a09.customers FORCE ROW LEVEL SECURITY")
        forced_owner = attempt(box, "a09_owner", count)[1][0][0]
        admin.execute("ALTER TABLE a09.customers NO FORCE ROW LEVEL SECURITY")
        superuser = admin.execute(count).fetchone()[0]
        admin.execute("CREATE ROLE a09_bypass LOGIN PASSWORD 'pw' BYPASSRLS")
        try:
            admin.execute("GRANT USAGE ON SCHEMA a09 TO a09_bypass")
            admin.execute("GRANT SELECT ON a09.customers TO a09_bypass")
            bypass = attempt(box, "a09_bypass", count)[1][0][0]
        finally:
            admin.execute("DROP OWNED BY a09_bypass")
            admin.execute("DROP ROLE a09_bypass")
    return {"owner_with_force": forced_owner, "superuser": superuser, "bypassrls_role": bypass}


# (ロール, SQL, 成功してよいか)。デプロイのたびに流し、期待と違うものを数える
GRANT_CHECKS = [
    ("a09_analyst", "SELECT email FROM a09.customers", False),
    ("a09_analyst", "SELECT phone FROM a09.customers", False),
    ("a09_analyst", "SELECT note FROM a09.orders", False),
    ("a09_analyst", "SELECT * FROM a09.audit_log", False),
    ("a09_analyst", "SELECT customer_id, prefecture FROM a09.customers", True),
    ("a09_analyst", "SELECT email FROM a09.customers_masked", True),
    ("a09_support", "SELECT email FROM a09.customers", False),
    ("a09_support", "DELETE FROM a09.customers", False),
    ("a09_etl", "DELETE FROM a09.audit_log", False),
]


def grant_regressions(box):
    """GRANT_CHECKS の期待と実際が食い違うものを返します。空なら権限は設計どおりです。"""
    return [(role, sql, expected) for role, sql, expected in GRANT_CHECKS
            if (attempt(box, role, sql)[0] == "ok") != expected]
