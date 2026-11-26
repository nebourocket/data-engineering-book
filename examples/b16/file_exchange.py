"""第16章: ファイルで渡す・読み取り専用で見せる・ノートブックから繋ぐ、の 3 つの小さな例。"""
import csv
import hashlib
import json
import os
from pathlib import Path

import duckdb

# 渡す列を決めます。name と email (個人情報) は入れません。
EXPORT_SQL = """
select customer_id, orders, lifetime_spend, last_order_date, segment
from customer_summary
order by customer_id
"""

SERVING_VIEW_SQL = """
create or replace view serving_customers as
select customer_id, orders, lifetime_spend, last_order_date, segment
from customer_summary
"""


def export_csv(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """CSV を書き終えてから、件数と SHA-256 を書いた manifest を置きます。受け取る側は manifest を待ちます。"""
    cursor = con.execute(EXPORT_SQL)
    header = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:  # BOM 付き: Windows の Excel が文字化けしないように
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    os.replace(tmp, path)  # 同じフォルダの中での名前変更なので、読む人には書きかけが見えない
    manifest = {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_name(path.name + ".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return len(rows)


def read_export(path: Path) -> list[dict]:
    """manifest の SHA-256 が合わなければ読まずに止めます。"""
    manifest = json.loads(path.with_name(path.name + ".manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("manifest と中身が合いません。書き直し中かもしれません")
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != manifest["rows"]:
        raise ValueError("件数が manifest と違います")
    return rows


def publish_view(path: Path) -> None:
    """提供用のビューを作ります。利用者にはこのビューだけを見せます。"""
    con = duckdb.connect(str(path))
    try:
        con.execute(SERVING_VIEW_SQL)
    finally:
        con.close()


def connect_for_notebook() -> duckdb.DuckDBPyConnection:
    """場所は環境変数から受け取り、読み取り専用で開きます。パスもパスワードもノートブックに書きません。"""
    path = os.environ.get("WAREHOUSE_PATH")
    if not path:
        raise RuntimeError("環境変数 WAREHOUSE_PATH が未設定です")
    return duckdb.connect(path, read_only=True)
