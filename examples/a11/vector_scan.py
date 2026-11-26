"""第11章: ベクトルの総当たり検索 (全件走査) の速さと、結果が正しいかを確かめます。乱数で作ったベクトルを使います。"""
import statistics
import time

import duckdb
import numpy as np

from embed_hash import DIM


def make_vectors(n, seed=0):
    """長さ 1 の乱数ベクトルを n 本作ります (float32)。"""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal((n, DIM)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def load(vectors):
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vecs (id INTEGER PRIMARY KEY, embedding FLOAT[{DIM}])")
    con.execute(f"INSERT INTO vecs SELECT i, v::FLOAT[{DIM}] FROM (SELECT unnest(?) AS v, generate_subscripts(?, 1) - 1 AS i)",
                [vectors.tolist(), vectors.tolist()])
    return con


def topk_duckdb(con, query, k):
    rows = con.execute(f"""SELECT id FROM vecs
        ORDER BY array_cosine_similarity(embedding, ?::FLOAT[{DIM}]) DESC, id LIMIT ?""", [query.tolist(), k]).fetchall()
    return [r[0] for r in rows]


def topk_numpy(vectors, query, k):
    """比べる側の独立な実装。内積の大きい順で、同点は番号の小さい順です。"""
    scores = vectors @ query
    order = sorted(range(len(vectors)), key=lambda i: (-float(scores[i]), i))
    return order[:k]


def median_seconds(con, query, k, repeat=5):
    seconds = []
    for _ in range(repeat):
        start = time.perf_counter()
        topk_duckdb(con, query, k)
        seconds.append(time.perf_counter() - start)
    return statistics.median(seconds)
