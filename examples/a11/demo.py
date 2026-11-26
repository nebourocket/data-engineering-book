"""第11章の出力をまとめて出します (外部サービスは要りません)。秒数は実行ごとに変わります。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))

import online_offline  # noqa: E402
import pit_features as pf  # noqa: E402
import rag_index  # noqa: E402
import shop_kb  # noqa: E402
import vector_scan  # noqa: E402


def show(title):
    print(f"--- {title}")


if __name__ == "__main__":
    show("point-in-time join")
    con = pf.load_shop()
    pf.build_labels(con)
    print("labels:", con.execute("SELECT t, count(*), sum(label) FROM labels GROUP BY t ORDER BY t").fetchall())
    for name, whole_day, how in [("pit", False, "pit"), ("stamped-by-date", True, "pit"), ("latest", False, "latest")]:
        pf.build_features(con, whole_day)
        rows = pf.joined(con, how)
        auc = pf.auc([r[4] for r in rows], [r[2] for r in rows])
        print(f"{name:16s} AUC={auc:.3f} {pf.leak_report(con, rows)}")
    pf.build_features(con, False)
    pf.assert_point_in_time(con, pf.joined(con, "pit"))
    try:
        pf.assert_point_in_time(con, pf.joined(con, "latest"))
    except pf.LeakError as e:
        print("latest ->", type(e).__name__)

    show("offline vs online")
    result, pairs = online_offline.run()
    print(f"pairs={pairs}")
    for name, (diff, rate) in result.items():
        print(f"{name:18s} mismatch={diff:4d} ({rate:.2%})")

    show("chunk size")
    for size in (60, 120, 240, 600):
        con = rag_index.new_index()
        added, _, _ = rag_index.sync_index(con, shop_kb.DOCS_V1, size)
        (h1, c1), (h3, c3) = (rag_index.hit_rate(con, shop_kb.QUERIES, k) for k in (1, 3))
        print(f"max_chars={size:3d} chunks={added:2d} hit@1={h1:.2f} hit@3={h3:.2f} chars@3={c3:.0f}")

    show("keep the index fresh")
    con = rag_index.new_index()
    print("v1 sync (added, kept, deleted):", rag_index.sync_index(con, shop_kb.DOCS_V1, 120))
    print("before:", rag_index.search(con, "返品は何日以内ですか", 1)[0][1])
    print("v2 sync (added, kept, deleted):", rag_index.sync_index(con, shop_kb.DOCS_V2, 120))
    print("after: ", rag_index.search(con, "返品は何日以内ですか", 1)[0][1])
    print("v2 again:", rag_index.sync_index(con, shop_kb.DOCS_V2, 120))
    full = rag_index.new_index()
    print("full rebuild of v2 embeds:", rag_index.sync_index(full, shop_kb.DOCS_V2, 120)[0])
    print("gift left:", [r[0] for r in rag_index.search(con, "ギフト包装の料金", 3) if "ギフト" in r[1]])

    show("edit position")
    short, long_ = "新しい一文です。", "ねぼすけ商店では、注文から発送、返品、返金までの流れを、次のとおり定めています。"
    for label, edit in (("short sentence at head", lambda t: short + t), ("short sentence at tail", lambda t: t + short),
                        ("long sentence at head", lambda t: long_ + t)):
        con = rag_index.new_index()
        rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
        docs = {**shop_kb.DOCS_V1, "orders-guide": edit(shop_kb.DOCS_V1["orders-guide"])}
        print(f"{label:24s} (added, kept, deleted) = {rag_index.sync_index(con, docs, 120)}")

    show("scan")
    for n in (1000, 10000, 100000):
        vecs = vector_scan.make_vectors(n)
        con = vector_scan.load(vecs)
        q = vector_scan.make_vectors(1, seed=99)[0]
        same = vector_scan.topk_duckdb(con, q, 5) == vector_scan.topk_numpy(vecs, q, 5)
        print(f"n={n:6d} same_as_numpy={same} median={vector_scan.median_seconds(con, q, 5) * 1000:.0f} ms")
