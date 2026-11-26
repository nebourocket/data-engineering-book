"""第9章の出力をこの順に出します: 権限・行レベル・マスク・監査 (PostgreSQL)、PII の探索、仮名化、削除。"""
import os
import tempfile

from govlab_access import (SETUP, access_matrix, audit_demo, grant_regressions, read_bypass, rls_exceptions,
                           row_level, who_touched)
from govlab_case import run
from govlab_erasure import build, erase, files_per_customer, touched
from govlab_lineage import pii_tables, pii_trail, unreviewed
from govlab_pg import sandbox
from lineage_events import one_night


def main():
    dsn = os.environ["PG_ADMIN_DSN"]  # ロールを作れる接続 (例: 使い捨ての PostgreSQL の postgres)
    with sandbox(dsn, SETUP) as box:
        print("== 権限 ==")
        for role, sql, status, result in access_matrix(box):
            print(f"{role:12} {status:5} {sql}\n{'':19}-> {result}")
        print("\n== 行レベルセキュリティ (count(*)) ==")
        for who, n in row_level(box).items():
            print(f"{who:22} {n}")
        print("\n== 行レベルセキュリティが効かない例 ==")
        for who, n in rls_exceptions(box).items():
            print(f"{who:22} {n}")
        print("\n== 権限の回帰チェック ==")
        print(f"期待と違うもの: {len(grant_regressions(box))} 件")
        print("\n== 監査ログ ==")
        audit = audit_demo(box)
        for actor, op, n in audit["summary"]:
            print(f"{actor:12} {op:12} {n}")
        for row in audit["reads"]:
            print("  参照", row)
        print("  改ざん:", audit["tamper"])
        print("\n== 監査の穴: 表を直接読む ==")
        before, after = read_bypass(box)
        print(f"a09_etl が顧客 8 を直接読む前後の READ の記録: {before} -> {after}")
        print("顧客 8 に誰が何をしたか:", who_touched(box, 8))

    print("\n== ケーススタディ ==")
    r = run()
    print("探索 (複製の前):")
    for (table, column, kind), n in r["scan_before"].items():
        print(f"  {table}.{column:6} {kind:5} {n:4} 行")
    print(f"メールのある顧客: {r['emails']} 人")
    print(f"ソルトなしの SHA-256 を辞書攻撃: {r['naive_recovered']} 人のメールが分かった")
    print(f"探索 (複製の後): {len(r['scan_after'])} 件")
    print(f"鍵つき HMAC を鍵なしで辞書攻撃: {r['hmac_recovered']} 人")
    print("k-匿名性 (k=5) の (小さいグループにいる人数, グループ数):")
    print(f"  本番 (都道府県, 生年)              {r['k_pref_year']}")
    print(f"  本番 (都道府県, 生年, 登録日)      {r['k_raw']}")
    print(f"  開発用 (地方, 十年, 登録月)        {r['k_dev_month']}")
    print(f"  開発用 (地方, 十年) 登録日を落とす {r['k_dev']}")
    print(f"開発用の注文と顧客を仮名化した番号で結べる行: {r['dev_key_shared']} / {r['orders']}")

    print("\n== リネージで PII の行き先をたどる ==")
    trail = pii_trail(one_night(), pii_tables(r["scan_before"]))
    for source, tables in trail.items():
        print(f"{source} -> {tables}")
    print("棚卸しが済んでいない行き先:", unreviewed(trail, ["raw.orders", "mart.fact_sales"]))

    print("\n== 削除の要求 (顧客 42) ==")
    with tempfile.TemporaryDirectory() as d:
        con, root = build(d)
        for name in ("by_month", "by_customer"):
            hit, total, hit_bytes, total_bytes = touched(con, root / name, 42)
            print(f"{name:12} 書き直すファイル {hit}/{total}  バイト {hit_bytes:,}/{total_bytes:,}")
        print("月ごとの置き方で、1 人の注文が散らばるファイル数 (平均, 最大):", files_per_customer(con))
        for name in ("by_month", "by_customer"):
            n = erase(con, root / name, 42)
            left = con.execute(
                f"SELECT count(*) FROM read_parquet('{root}/{name}/*/*.parquet', hive_partitioning=false) "
                "WHERE customer_id = 42").fetchone()[0]
            print(f"{name:12} 書き直した {n} ファイル、消した後の残り {left} 行")


if __name__ == "__main__":
    main()
