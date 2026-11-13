"""文字コード（UTF-8・Shift_JIS 系・BOM）と Unicode 正規化の実験です。"""
import unicodedata

text = "ねぼすけ商店"
utf8 = text.encode("utf-8")
cp932 = text.encode("cp932")  # Windows の日本語環境が使う Shift_JIS 系
print(len(text), "文字", len(utf8), "バイト(UTF-8)", len(cp932), "バイト(cp932)")

# 書いた文字コードと違う文字コードで読むと文字化けする（読めないバイトは ? に置き換える）
print(utf8.decode("cp932", errors="replace"))
print(cp932.decode("utf-8", errors="replace"))

# Excel で開きやすいように BOM 付き UTF-8 で書かれた CSV の先頭
csv_bytes = "order_id,商品名\n1,枕\n".encode("utf-8-sig")
print(csv_bytes[:3], csv_bytes[:3].hex())
print(repr(csv_bytes.decode("utf-8").splitlines()[0]))  # BOM が列名にくっつく
print(repr(csv_bytes.decode("utf-8-sig").splitlines()[0]))  # BOM を取り除く

# 見た目が同じでも、並べ方の違う文字列（NFC と NFD）
composed = "ガ"  # 1 コードポイント（U+30AC）
decomposed = unicodedata.normalize("NFD", composed)  # カ + 濁点（2 コードポイント）
print(composed == decomposed, len(composed), len(decomposed))
print(unicodedata.normalize("NFC", decomposed) == composed)
