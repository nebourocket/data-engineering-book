"""第11章のコードの検査。リークの検出・食い違いの数・検索の正しさを確かめます (秒数は見ません)。"""
import itertools

import pytest

import embed_hash
import online_offline
import pit_features as pf
import rag_index
import shop_kb
import vector_scan


def brute_auc(scores, labels):
    """全ての (正例, 負例) の組を数える定義どおりの AUC (同点は 0.5)。"""
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p, n in itertools.product(pos, neg))
    return wins / (len(pos) * len(neg))


def test_auc_matches_the_pairwise_definition_including_ties():
    scores = [3, 1, 2, 2, 5, 1, 2, 4]
    labels = [1, 0, 0, 1, 1, 0, 1, 0]
    assert pf.auc(scores, labels) == pytest.approx(brute_auc(scores, labels))
    assert pf.auc([1, 2, 3, 4], [0, 0, 1, 1]) == 1.0
    with pytest.raises(ValueError):
        pf.auc([1, 2], [1, 1])


@pytest.fixture(scope="module")
def shop():
    con = pf.load_shop()
    pf.build_labels(con)
    return con


def test_labels_per_cutoff(shop):
    rows = shop.execute("SELECT t, count(*), sum(label) FROM labels GROUP BY t ORDER BY t").fetchall()
    assert [(r[1], r[2]) for r in rows] == [(322, 273), (505, 390), (505, 236)]


def test_point_in_time_join_is_clean_and_latest_join_leaks(shop):
    pf.build_features(shop, whole_day=False)
    pit, latest = pf.joined(shop, "pit"), pf.joined(shop, "latest")
    assert pf.assert_point_in_time(shop, pit) == {"rows": 1332, "after_t": 0, "wrong_value": 0, "missing": 0}
    assert pf.leak_report(shop, latest) == {"rows": 1332, "after_t": 1332, "wrong_value": 991, "missing": 0}
    with pytest.raises(pf.LeakError):
        pf.assert_point_in_time(shop, latest)
    assert round(pf.auc([r[4] for r in pit], [r[2] for r in pit]), 3) == 0.278
    assert round(pf.auc([r[4] for r in latest], [r[2] for r in latest]), 3) == 0.625


def test_date_stamp_mistake_passes_the_timestamp_check_but_not_the_recount(shop):
    pf.build_features(shop, whole_day=True)
    rows = pf.joined(shop, "pit")
    report = pf.leak_report(shop, rows)
    assert (report["after_t"], report["wrong_value"]) == (0, 65)  # 印は t 以前なのに、値には未来が入っている
    with pytest.raises(pf.LeakError):
        pf.assert_point_in_time(shop, rows)
    assert round(pf.auc([r[4] for r in rows], [r[2] for r in rows]), 3) == 0.286


def test_leak_check_refuses_an_empty_join(shop):
    with pytest.raises(pf.LeakError):
        pf.leak_report(shop, [])


def test_online_offline_mismatch_counts():
    result, pairs = online_offline.run()
    assert pairs == 87365
    assert {k: v[0] for k, v in result.items()} == {"event_time_dedup": 222, "no_dedup": 485, "known_at_t": 0}


def test_skew_refuses_different_key_sets():
    with pytest.raises(ValueError):
        online_offline.skew({(1, 1): 0}, {(1, 2): 0})


def test_embedding_is_deterministic_and_unit_length():
    v = embed_hash.embed("返品は何日以内ですか")
    assert v == embed_hash.embed("返品は何日以内ですか")
    assert len(v) == embed_hash.DIM and sum(x * x for x in v) == pytest.approx(1.0)
    one = embed_hash.embed("返品")  # 2 字組が 1 つだけ: 0 でない位置が 1 つ
    assert [i for i, x in enumerate(one) if x] == [100] and abs(one[100]) == 1.0
    assert embed_hash.embed("") == [0.0] * embed_hash.DIM


def test_chunks_are_lossless_and_bounded():
    for text in shop_kb.DOCS_V1.values():
        for size in (60, 120, 240):
            chunks = rag_index.chunk(text, size)
            assert "".join(chunks) == text
            assert all(len(c) <= size or c.count("。") == 1 for c in chunks)


def test_hit_rate_by_chunk_size():
    got = {}
    for size in (60, 120, 240, 600):
        con = rag_index.new_index()
        rag_index.sync_index(con, shop_kb.DOCS_V1, size)
        (h1, _), (h3, chars) = (rag_index.hit_rate(con, shop_kb.QUERIES, k) for k in (1, 3))
        got[size] = (h1, h3, round(chars))
    assert got == {60: (0.65, 0.85, 139), 120: (0.7, 0.85, 280), 240: (0.8, 1.0, 512), 600: (0.75, 1.0, 1132)}


def test_incremental_sync_embeds_only_what_changed():
    con = rag_index.new_index()
    assert rag_index.sync_index(con, shop_kb.DOCS_V1, 120) == (16, 0, 0)
    assert "7 日以内" in rag_index.search(con, "返品は何日以内ですか", 1)[0][1]
    assert rag_index.sync_index(con, shop_kb.DOCS_V2, 120) == (3, 13, 3)
    assert "14 日以内" in rag_index.search(con, "返品は何日以内ですか", 1)[0][1]
    assert rag_index.sync_index(con, shop_kb.DOCS_V2, 120) == (0, 16, 0)
    assert not any("ギフト" in r[1] for r in rag_index.search(con, "ギフト包装の料金", 16))
    assert con.execute("SELECT count(*) FROM chunks WHERE text LIKE '%7 日以内に受け付けます%'").fetchall() == [(0,)]
    # 差分で作った索引と、最初から作った索引の中身が同じ
    fresh = rag_index.new_index()
    rag_index.sync_index(fresh, shop_kb.DOCS_V2, 120)
    q = "SELECT doc_id, content_hash FROM chunks ORDER BY 1, 2"
    assert con.execute(q).fetchall() == fresh.execute(q).fetchall()


def test_sync_refuses_to_wipe_the_index_on_empty_input():
    con = rag_index.new_index()
    rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
    with pytest.raises(ValueError):
        rag_index.sync_index(con, {}, 120)
    assert con.execute("SELECT count(*) FROM chunks").fetchall() == [(16,)]


def test_a_removed_document_disappears():
    con = rag_index.new_index()
    rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
    rest = {k: v for k, v in shop_kb.DOCS_V1.items() if k != "account-guide"}
    assert rag_index.sync_index(con, rest, 120)[2] == 3
    assert "account-guide" not in {r[0] for r in rag_index.search(con, "パスワードを忘れました", 16)}


def test_duckdb_scan_matches_numpy_including_ties():
    vecs = vector_scan.make_vectors(2000)
    vecs[7] = vecs[3]  # 同じベクトル: 同点は番号の小さい順
    con = vector_scan.load(vecs)
    for seed in (1, 2, 3):
        q = vector_scan.make_vectors(1, seed=seed)[0]
        assert vector_scan.topk_duckdb(con, q, 5) == vector_scan.topk_numpy(vecs, q, 5)
    q = vecs[3]
    top = vector_scan.topk_duckdb(con, q, 3)
    assert top[:2] == [3, 7]


def test_top3_misses_at_small_chunk_sizes_are_these_questions():
    misses = {}
    for size in (60, 120, 240):
        con = rag_index.new_index()
        rag_index.sync_index(con, shop_kb.DOCS_V1, size)
        misses[size] = [q for q, answer in shop_kb.QUERIES
                        if not any(answer in text for _, text, _ in rag_index.search(con, q, 3))]
    assert misses == {
        60: ["代金引換の手数料はいくらですか", "誕生日に何かもらえますか", "コーヒー豆は冷蔵庫で保存できますか"],
        120: ["代金引換の手数料はいくらですか", "誕生日に何かもらえますか", "枕を干すときの注意"],
        240: []}


@pytest.mark.parametrize("where", ["head", "tail"])
def test_adding_one_short_sentence_changes_one_chunk(where):
    con = rag_index.new_index()
    rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
    docs = dict(shop_kb.DOCS_V1)
    text = docs["orders-guide"]
    docs["orders-guide"] = "新しい一文です。" + text if where == "head" else text + "新しい一文です。"
    assert rag_index.sync_index(con, docs, 120) == (1, 15, 1)


def _snapshot(con):
    return con.execute("SELECT doc_id, content_hash, text FROM chunks ORDER BY 1, 2").fetchall()


def test_sync_refuses_blank_documents_and_leaves_the_index_alone():
    con = rag_index.new_index()
    rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
    before = _snapshot(con)
    for bad in ({"x": ""}, {"x": "  \n"}, {**shop_kb.DOCS_V1, "x": ""}):
        with pytest.raises(ValueError):
            rag_index.sync_index(con, bad, 120)
    assert _snapshot(con) == before


def test_sync_refuses_a_large_delete_share_unless_allowed():
    con = rag_index.new_index()
    rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
    before = _snapshot(con)
    only_one = {"account-guide": shop_kb.DOCS_V1["account-guide"]}
    with pytest.raises(ValueError, match="削除"):
        rag_index.sync_index(con, only_one, 120)
    assert _snapshot(con) == before
    assert rag_index.sync_index(con, only_one, 120, max_delete_share=1.0) == (0, 3, 13)


def test_sync_is_atomic_when_embedding_fails_midway(monkeypatch):
    con = rag_index.new_index()
    rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
    before = _snapshot(con)
    calls = []

    def flaky(text):
        calls.append(text)
        if len(calls) == 2:
            raise RuntimeError("埋め込みの失敗")
        return embed_hash.embed(text)

    monkeypatch.setattr(rag_index, "embed", flaky)
    with pytest.raises(RuntimeError):
        rag_index.sync_index(con, shop_kb.DOCS_V2, 120)
    assert _snapshot(con) == before  # 削除も追加も起きていない


def test_sync_rolls_back_deletes_when_an_insert_fails(monkeypatch):
    con = rag_index.new_index()
    rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
    before = _snapshot(con)
    calls = []

    def short_vector(text):
        calls.append(text)
        return embed_hash.embed(text) if len(calls) == 1 else [0.0] * 3  # 2 本目は長さが違う

    monkeypatch.setattr(rag_index, "embed", short_vector)
    with pytest.raises(Exception):
        rag_index.sync_index(con, shop_kb.DOCS_V2, 120)
    assert _snapshot(con) == before  # 先に走った削除も戻っている


def test_a_long_sentence_at_the_head_shifts_several_chunks():
    con = rag_index.new_index()
    rag_index.sync_index(con, shop_kb.DOCS_V1, 120)
    docs = dict(shop_kb.DOCS_V1)
    docs["orders-guide"] = "ねぼすけ商店では、注文から発送、返品、返金までの流れを、次のとおり定めています。" + docs["orders-guide"]
    assert rag_index.sync_index(con, docs, 120) == (3, 13, 3)


def test_point_in_time_check_refuses_rows_without_features(shop):
    pf.build_features(shop, whole_day=False)
    rows = pf.joined(shop, "pit")
    holed = [r[:3] + (None, None) for r in rows[:5]] + rows[5:]
    assert pf.leak_report(shop, holed)["missing"] == 5
    with pytest.raises(pf.LeakError, match="付かない"):
        pf.assert_point_in_time(shop, holed)
    assert pf.assert_point_in_time(shop, holed, max_missing=5)["missing"] == 5
