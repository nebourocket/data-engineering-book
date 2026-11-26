"""共通の架空データセット「ねぼすけ商店」を作ります。

朝が苦手な人向けの小さなオンライン雑貨店、という設定です。どの章でも同じデータを使えるよう、
同じ seed なら必ず同じ結果になります（標準ライブラリだけで動きます）。

テーブル（generate() が返す dict のキー）:
    customers   顧客約 500 件。customer_id, name, email, prefecture, registered_at
    products    商品 52 件。product_id, name, category, price
    orders      注文約 3,000 件。order_id, customer_id, ordered_at, status
    order_items 注文明細。order_id, line_no, product_id, quantity, unit_price
    events      行動ログ。event_id, customer_id, event_type, event_time, received_at

意図的に入れてあるデータの欠陥（13 章のデータ品質などで使います）:
    1. customers.email が約 5% 欠けています（None）。
    2. customers に同じメールアドレスで customer_id だけ違う重複登録が数件あります。
    3. orders.status に表記ゆれ（"shipped" と "SHIPPED"）が少し混ざっています。
    4. events の一部が重複して届いています（同じ event_id が 2 回出ます）。
    5. events の一部は遅れて届きます（received_at が event_time の翌日以降）。

日時は "YYYY-MM-DD HH:MM:SS" 形式の文字列です（並べ替えがそのまま時刻順になります）。
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

START = datetime(2026, 1, 1)
DAYS = 180

PREFECTURES = ["北海道", "宮城", "東京", "神奈川", "愛知", "石川", "大阪", "京都", "福岡", "沖縄"]
CATEGORIES = {
    "寝具": ["枕", "毛布", "アイマスク", "シーツ", "抱き枕", "布団カバー"],
    "目覚まし": ["置き時計", "光る目覚まし", "振動リスト", "ベル式時計"],
    "飲み物": ["コーヒー豆", "紅茶", "エナジードリンク", "ココア", "緑茶", "麦茶"],
    "朝食": ["トースト用パン", "ジャム", "シリアル", "はちみつ", "グラノーラ"],
    "雑貨": ["マグカップ", "ステッカー", "メモ帳", "ペン", "ブランケット"],
}
FAMILY = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤"]
GIVEN = ["太郎", "花子", "健", "美咲", "翔", "陽菜", "大輔", "愛", "蓮", "結衣"]
EVENT_TYPES = ["view", "view", "view", "add_to_cart", "search", "purchase"]


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def generate(seed: int = 42) -> dict[str, list[dict]]:
    """データセット全体を作ります。同じ seed なら同じ結果です。"""
    rng = random.Random(seed)

    products = []
    pid = 1
    for category, names in CATEGORIES.items():
        for name in names:
            for variant in ("標準", "大"):
                products.append({
                    "product_id": pid, "name": f"{name}({variant})", "category": category,
                    "price": rng.randrange(300, 6000, 50)})
                pid += 1

    customers = []
    for cid in range(1, 501):
        email = f"user{cid:04d}@example.com" if rng.random() > 0.05 else None
        customers.append({
            "customer_id": cid,
            "name": rng.choice(FAMILY) + rng.choice(GIVEN),
            "email": email,
            "prefecture": rng.choice(PREFECTURES),
            "registered_at": _fmt(START + timedelta(seconds=rng.randrange(DAYS // 2 * 86400)))})
    for dup in rng.sample(customers[:500], 6):  # 欠陥 2: 同じメールの二重登録
        if dup["email"]:
            customers.append({**dup, "customer_id": len(customers) + 1})

    orders, items = [], []
    for oid in range(1, 3001):
        c = rng.choice(customers)
        ordered = datetime.strptime(c["registered_at"], "%Y-%m-%d %H:%M:%S") + timedelta(
            seconds=rng.randrange(DAYS * 86400 // 2))
        status = rng.choice(["placed", "shipped", "shipped", "delivered", "delivered", "cancelled"])
        if status == "shipped" and rng.random() < 0.05:
            status = "SHIPPED"  # 欠陥 3: 表記ゆれ
        orders.append({"order_id": oid, "customer_id": c["customer_id"],
                       "ordered_at": _fmt(ordered), "status": status})
        for line_no in range(1, rng.randint(1, 4) + 1):
            p = rng.choice(products)
            items.append({"order_id": oid, "line_no": line_no, "product_id": p["product_id"],
                          "quantity": rng.randint(1, 3), "unit_price": p["price"]})

    events = []
    for eid in range(1, 4001):
        c = rng.choice(customers)
        t = START + timedelta(seconds=rng.randrange(DAYS * 86400))
        late = rng.random() < 0.03  # 欠陥 5: 遅れて届く
        received = t + (timedelta(days=rng.randint(1, 3), seconds=rng.randrange(3600)) if late
                        else timedelta(seconds=rng.randrange(1, 30)))
        events.append({"event_id": eid, "customer_id": c["customer_id"],
                       "event_type": rng.choice(EVENT_TYPES),
                       "event_time": _fmt(t), "received_at": _fmt(received)})
    for e in rng.sample(events, 40):  # 欠陥 4: 二重に届く
        events.append(dict(e))
    events.sort(key=lambda e: (e["received_at"], e["event_id"]))

    return {"customers": customers, "products": products, "orders": orders,
            "order_items": items, "events": events}


def write_duckdb(path, seed: int = 42) -> None:
    """DuckDB のファイルに全テーブルを書きます（既にあるテーブルは作り直します）。"""
    import duckdb
    import pyarrow as pa

    con = duckdb.connect(str(path))
    try:
        for name, rows in generate(seed).items():
            con.register("_t", pa.Table.from_pylist(rows))
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _t")
            con.unregister("_t")
    finally:
        con.close()


def write_parquet(directory, seed: int = 42) -> None:
    """directory/<テーブル名>.parquet として書きます。"""
    import pyarrow as pa
    import pyarrow.parquet as pq

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in generate(seed).items():
        pq.write_table(pa.Table.from_pylist(rows), out / f"{name}.parquet")


if __name__ == "__main__":
    for table, rows in generate().items():
        print(table, len(rows))
