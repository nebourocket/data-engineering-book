"""第11章: 学習済みモデルを使わない決定的な埋め込み。文字 2 字組 (bigram) をハッシュで 256 次元に落とした、語の一致に基づくベクトルです。"""
import hashlib
import math

DIM = 256


def bigrams(text):
    """空白と句読点を除いた文字列の 2 字組。1 文字しかなければその 1 文字を返す。"""
    chars = [ch for ch in text if ch.isalnum()]
    if len(chars) < 2:
        return chars
    return ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]


def embed(text, dim=DIM):
    """2 字組の出現回数を (1 + log 回数) にして、ハッシュの位置へ足し、長さ 1 に直します。
    Python 組み込みの hash() は実行ごとに変わるので、md5 の先頭 8 バイトを使います。"""
    counts = {}
    for g in bigrams(text):
        counts[g] = counts.get(g, 0) + 1
    vec = [0.0] * dim
    for g, n in counts.items():
        h = int.from_bytes(hashlib.md5(g.encode("utf-8")).digest()[:8], "big")
        vec[h % dim] += (1 + math.log(n)) * (1 if (h >> 63) & 1 else -1)
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec
