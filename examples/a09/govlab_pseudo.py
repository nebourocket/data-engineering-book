"""パイプラインの中で PII を扱う: マスク・仮名化 (ハッシュと HMAC)・k-匿名性。"""
import hashlib
import hmac
import re


def mask_email(email):
    """先頭 1 文字と @ 以降だけ残します。None はそのまま None。"""
    return None if email is None else re.sub(r"^(.)[^@]*", r"\1***", email)


def plain_hash(value):
    """ソルトも鍵もない SHA-256 (先頭 16 文字)。同じ入力は誰が計算しても同じ値になります。"""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def keyed_hash(value, key):
    """鍵つきの HMAC-SHA256 (先頭 16 文字)。鍵を持つ人だけが同じ値を作れます。"""
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:16]


def guess_emails():
    """攻撃者が「user + 4 桁 + @example.com だろう」と推測して作る候補 (1〜9999)。"""
    return [f"user{i:04d}@example.com" for i in range(1, 10000)]


def dictionary_attack(hashes, hash_func):
    """候補を同じ関数でハッシュし、hashes と一致した数 (= 元のメールが分かった数) を返します。"""
    table = {hash_func(candidate): candidate for candidate in guess_emails()}
    return sum(1 for h in hashes if h in table)


def small_groups(con, table, columns, k=5):
    """表 table で、columns の組が同じ人が k 人未満のグループにいる人数と、グループ数を返します。"""
    cols = ", ".join(columns)
    return con.execute(
        f"SELECT coalesce(sum(n) FILTER (WHERE n < {k}), 0)::INTEGER, count(*)::INTEGER "
        f"FROM (SELECT count(*) AS n FROM {table} GROUP BY {cols})").fetchone()
