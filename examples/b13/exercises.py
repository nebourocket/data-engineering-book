"""練習問題の解答例。pytest (test_b13_quality.py) で動かして確かめています。"""
from quality import Check, not_null

# 問 1: メールの欠けを 3% まで許す error。実測は約 3.96% なので止まる。
EMAIL_STRICT = not_null("customers", "email", severity="error", max_ratio=0.03)

# 追加の例: 数量が 1 以上であること (範囲の確認)。
QUANTITY_POSITIVE = Check(
    "order_items.quantity_positive", "正確さ", "error",
    "SELECT count(*) FILTER (WHERE quantity < 1), count(*) FROM order_items")

# 問 3 (単価): order_items.unit_price が products.price と違う行を数える。
# 値段の食い違いは売上を直接ゆがめるので、後から直しにくい数字として error にする。
PRICE_MATCHES = Check(
    "order_items.unit_price_matches_products", "正確さ", "error",
    "SELECT count(*) FILTER (WHERE i.unit_price <> p.price), count(*) "
    "FROM order_items AS i JOIN products AS p ON i.product_id = p.product_id")

# 問 4 (既知の欠陥): 受信が発生より前の行 (時計のずれ) を warn で数える。
RECEIVED_BEFORE_EVENT = Check(
    "events.received_not_before_event", "正確さ", "warn",
    "SELECT count(*) FILTER (WHERE received_at < event_time), count(*) FROM events")
