-- ミニディメンション: 変わりやすい属性の組み合わせだけを小さな表にする
CREATE TABLE dim_customer_profile (profile_key integer PRIMARY KEY, engagement text, tier text);
-- ファクトには、取引の時点の組み合わせを指す profile_key を持たせる
-- 例: fact_sales (order_id, line_no, customer_key, profile_key, amount)
