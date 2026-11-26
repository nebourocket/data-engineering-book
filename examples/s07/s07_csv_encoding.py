"""文字コードと BOM の違いを、ファイルの先頭のバイトで確かめます。"""
import csv
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as folder:
    plain = Path(folder) / "plain.csv"
    with_bom = Path(folder) / "with_bom.csv"
    for path, encoding in ((plain, "utf-8"), (with_bom, "utf-8-sig")):
        with open(path, "w", encoding=encoding, newline="") as f:
            csv.writer(f).writerows([["注文番号", "商品"], [1001, "アイマスク"]])

    # 先頭の 3 バイト。BOM があると EF BB BF が付く
    print(plain.read_bytes()[:3].hex(" "))
    print(with_bom.read_bytes()[:3].hex(" "))

    # BOM 付きのファイルを、BOM を知らない読み方 (utf-8) で読むと、見出しの先頭に見えない文字が入る
    with open(with_bom, encoding="utf-8", newline="") as f:
        print(next(csv.reader(f)))
    with open(with_bom, encoding="utf-8-sig", newline="") as f:
        print(next(csv.reader(f)))

    # 別の文字コード (cp932) で書いたファイルを utf-8 で読もうとすると、読めない
    legacy = Path(folder) / "legacy.csv"
    legacy.write_bytes("注文番号,商品\n".encode("cp932"))
    try:
        legacy.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        print(type(error).__name__)
