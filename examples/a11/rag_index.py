"""第11章: 文書を分割 (チャンク化) し、ベクトルにして DuckDB の配列列へ入れ、類似度で検索します。更新は差分だけ入れ直します。"""
import hashlib

import duckdb

from embed_hash import DIM, embed


def chunk(text, max_chars):
    """文 (。で区切る) を max_chars 以内に詰めて、チャンクの一覧にします。1 文が長ければ、その文が 1 チャンクです。"""
    sentences = [s + "。" for s in text.split("。") if s]
    chunks, current = [], ""
    for s in sentences:
        if current and len(current) + len(s) > max_chars:
            chunks.append(current)
            current = ""
        current += s
    if current:
        chunks.append(current)
    return chunks


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def new_index():
    con = duckdb.connect()
    con.execute(f"""CREATE TABLE chunks (
        doc_id VARCHAR, content_hash VARCHAR, text VARCHAR, embedding FLOAT[{DIM}],
        PRIMARY KEY (doc_id, content_hash))""")
    return con


def wanted(docs, max_chars):
    """文書の一覧から、(doc_id, hash) -> テキスト の対応を作ります。同じ文書内の同じ文は 1 つにします。"""
    out = {}
    for doc_id, text in docs.items():
        for c in chunk(text, max_chars):
            out.setdefault((doc_id, digest(c)), c)
    return out


def sync_index(con, docs, max_chars, max_delete_share=0.5):
    """インデックスを docs の内容に合わせます。変わらないチャンクは埋め込み直さず、消えたチャンクは削除します。
    先に追加分をすべて埋め込み、削除と追加は 1 つのトランザクションで行うので、途中で失敗しても元のままです。
    文書が空・チャンクが 0 件・削除が既存の max_delete_share を超えるときは、何も変えずに ValueError にします。
    戻り値は (追加して埋め込んだ数, 変わらなかった数, 削除した数)。"""
    if not docs or any(not text.strip() for text in docs.values()):
        raise ValueError("文書が 0 件、または空の文書があります。取り込みの失敗で全件を消さないよう、同期を止めます")
    target = wanted(docs, max_chars)
    if not target:
        raise ValueError("チャンクが 0 件です。同期を止めます")
    have = {(d, h) for d, h in con.execute("SELECT doc_id, content_hash FROM chunks").fetchall()}
    to_add = [k for k in target if k not in have]
    to_delete = [k for k in have if k not in target]
    if have and len(to_delete) / len(have) > max_delete_share:
        raise ValueError(f"削除が {len(to_delete)}/{len(have)} 件で、上限 {max_delete_share:.0%} を超えます。同期を止めます")
    vectors = [embed(target[k]) for k in to_add]  # 失敗するならここ (まだ何も変えていない)
    con.execute("BEGIN")
    try:
        for doc_id, h in to_delete:
            con.execute("DELETE FROM chunks WHERE doc_id = ? AND content_hash = ?", [doc_id, h])
        for (doc_id, h), vec in zip(to_add, vectors):
            con.execute(f"INSERT INTO chunks VALUES (?, ?, ?, ?::FLOAT[{DIM}])", [doc_id, h, target[(doc_id, h)], vec])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(to_add), len(have) - len(to_delete), len(to_delete)


def search(con, query, k=3):
    """コサイン類似度の高い順に k 件。同点は doc_id と hash で順序を決めます。"""
    return con.execute(f"""
        SELECT doc_id, text, array_cosine_similarity(embedding, ?::FLOAT[{DIM}]) AS score
        FROM chunks ORDER BY score DESC, doc_id, content_hash LIMIT ?""", [embed(query), k]).fetchall()


def hit_rate(con, queries, k):
    """上位 k 件のチャンクのどれかに答えの語が含まれる質問の割合と、渡すことになる文字数の平均を返します。"""
    if not queries:
        raise ValueError("質問がありません")
    hits, chars = 0, 0
    for query, answer in queries:
        top = search(con, query, k)
        hits += any(answer in text for _, text, _ in top)
        chars += sum(len(text) for _, text, _ in top)
    return hits / len(queries), chars / len(queries)
