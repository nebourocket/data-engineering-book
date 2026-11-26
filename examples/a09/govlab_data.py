"""第9章のデータ: ねぼすけ商店に、電話番号・生年・注文メモ (自由記述) を足します。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
from neboske_shop import generate  # noqa: E402

PREFECTURES_BY_REGION = {
    "北海道": "北海道", "宮城": "東北", "東京": "関東", "神奈川": "関東", "愛知": "中部", "石川": "中部",
    "大阪": "近畿", "京都": "近畿", "福岡": "九州沖縄", "沖縄": "九州沖縄",
}


def load_shop():
    """顧客 506 件と注文 3,000 件。同じ入力なら必ず同じ結果です。"""
    shop = generate()
    customers = []
    for c in shop["customers"]:
        cid = c["customer_id"]
        customers.append({
            **c,
            "phone": f"090-{cid:04d}-{(cid * 7919) % 10000:04d}",
            "birth_year": 1950 + (cid * 37) % 56,  # 1950〜2005 年
        })
    orders = []
    for o in shop["orders"]:
        oid = o["order_id"]
        note = ""
        if oid % 37 == 0:
            note = f"届かない場合は 090-{oid:04d}-1234 へ電話してください"
        elif oid % 53 == 0:
            note = f"領収書は user{oid:04d}@example.com へ"
        elif oid % 11 == 0:
            note = "ギフト包装希望"
        orders.append({**o, "note": note})
    return customers, orders
