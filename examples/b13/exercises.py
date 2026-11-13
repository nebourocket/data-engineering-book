"""練習問題の解答例。pytest (test_b13_quality.py) で動かして確かめています。"""
from quality import Check, not_null

# 問 1: メールの欠けを 3% まで許す error。実測は約 3.96% なので止まる。
EMAIL_STRICT = not_null("customers", "email", severity="error", max_ratio=0.03)

# 問 3: 自分で Check を書く。数量が 1 以上であること (範囲の確認)。
QUANTITY_POSITIVE = Check(
    "order_items.quantity_positive", "正確さ", "error",
    "SELECT count(*) FILTER (WHERE quantity < 1), count(*) FROM order_items")
