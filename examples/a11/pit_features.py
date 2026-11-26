"""第11章: 特徴量のポイントインタイム結合。リークする結合と正しい結合を DuckDB で作り、AUC と突き合わせで測ります。"""
from datetime import datetime, timedelta

import duckdb
import pyarrow as pa

from neboske_shop import generate

LABEL_DAYS = 30
CUTOFFS = [datetime(2026, 3, 1), datetime(2026, 4, 1), datetime(2026, 5, 1)]
CALENDAR_START = datetime(2026, 1, 1)
CALENDAR_DAYS = 181


class LeakError(Exception):
    """特徴量が、予測する時刻より後の情報を含んでいたときの例外。"""


def load_shop():
    """ねぼすけ商店の顧客と注文を DuckDB に載せます (日時は TIMESTAMP に直す)。"""
    data = generate()
    con = duckdb.connect()
    con.register("c_arrow", pa.Table.from_pylist(data["customers"]))
    con.register("o_arrow", pa.Table.from_pylist(data["orders"]))
    con.execute("CREATE TABLE customers AS SELECT customer_id, CAST(registered_at AS TIMESTAMP) AS registered_at FROM c_arrow")
    con.execute("CREATE TABLE orders AS SELECT order_id, customer_id, CAST(ordered_at AS TIMESTAMP) AS ordered_at FROM o_arrow")
    return con


def build_features(con, whole_day):
    """顧客 x 日の特徴量表 features を作ります。値は「それまでの累計の注文数」です。
    whole_day=False: 日の 0 時より前の注文だけを数える (0 時に使える値)。
    whole_day=True : その日の注文まで数えて、日の 0 時の印を付ける (よくある日付の付け間違い)。"""
    extra = "+ INTERVAL 1 DAY" if whole_day else ""
    con.execute(f"""
        CREATE OR REPLACE TABLE features AS
        SELECT c.customer_id, d.ts AS feature_ts, count(o.order_id) AS lifetime_orders
        FROM customers c
        CROSS JOIN (SELECT CAST(unnest(generate_series(TIMESTAMP '2026-01-01', TIMESTAMP '2026-06-30', INTERVAL 1 DAY)) AS TIMESTAMP) AS ts) d
        LEFT JOIN orders o ON o.customer_id = c.customer_id AND o.ordered_at < d.ts {extra}
        GROUP BY c.customer_id, d.ts""")


def build_labels(con):
    """予測の時刻 t ごとに「次の 30 日に注文したか」の正解を作ります。t より前に登録した顧客だけが対象です。"""
    parts = []
    for t in CUTOFFS:
        parts.append(f"""
            SELECT c.customer_id, TIMESTAMP '{t:%Y-%m-%d}' AS t,
                   CAST(EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id
                                AND o.ordered_at >= TIMESTAMP '{t:%Y-%m-%d}'
                                AND o.ordered_at < TIMESTAMP '{t:%Y-%m-%d}' + INTERVAL {LABEL_DAYS} DAY) AS INTEGER) AS label
            FROM customers c WHERE c.registered_at < TIMESTAMP '{t:%Y-%m-%d}'""")
    con.execute("CREATE OR REPLACE TABLE labels AS " + " UNION ALL ".join(parts))


JOIN_SQL = {
    # t より前で最も新しい特徴量の行を 1 本だけ付ける (ポイントインタイム結合)
    "pit": """SELECT l.customer_id, l.t, l.label, f.feature_ts, f.lifetime_orders
              FROM labels l ASOF LEFT JOIN features f
                ON l.customer_id = f.customer_id AND l.t >= f.feature_ts""",
    # 顧客ごとの最新の行を付ける (予測の時刻を見ていない)
    "latest": """SELECT l.customer_id, l.t, l.label, f.feature_ts, f.lifetime_orders
                 FROM labels l JOIN (
                   SELECT customer_id, max(feature_ts) AS feature_ts, arg_max(lifetime_orders, feature_ts) AS lifetime_orders
                   FROM features GROUP BY customer_id) f USING (customer_id)""",
}


def joined(con, how):
    return con.execute(JOIN_SQL[how] + " ORDER BY customer_id, t").fetchall()


def auc(scores, labels):
    """AUC (正例が負例より高いスコアを持つ確率)。順位和で求め、同点は平均順位にします。"""
    pairs = sorted(zip(scores, labels))
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    n_pos = sum(label for _, label in pairs)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("正例と負例の両方が要ります")
    rank_sum = sum(r for r, (_, label) in zip(ranks, pairs) if label == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def leak_report(con, rows):
    """結合結果を 2 通りで検査します。
    after_t: 特徴量の印 (feature_ts) が予測の時刻 t より後の行。
    wrong_value: t より前の注文だけで数え直した値と食い違う行 (特徴量が付かなかった行は missing として別に数える)。"""
    if not rows:
        raise LeakError("結合結果が空です")
    after_t = sum(1 for r in rows if r[3] is not None and r[3] > r[1])
    missing = sum(1 for r in rows if r[3] is None)
    con.register("joined_rows", pa.Table.from_pylist(
        [{"customer_id": r[0], "t": r[1], "value": r[4]} for r in rows]))
    wrong_value = con.execute("""
        SELECT count(*) FROM joined_rows j
        WHERE j.value IS NOT NULL AND j.value != (SELECT count(*) FROM orders o
                                        WHERE o.customer_id = j.customer_id AND o.ordered_at < j.t)""").fetchall()[0][0]
    con.unregister("joined_rows")
    return {"rows": len(rows), "after_t": after_t, "wrong_value": wrong_value, "missing": missing}


def assert_point_in_time(con, rows, max_missing=0):
    """リークがあれば LeakError。印の検査だけでなく、数え直した値との突き合わせにも通る必要があります。
    特徴量が付かなかった行 (missing) が max_missing を超えても失敗です (黙って NULL を学習に流さない)。"""
    report = leak_report(con, rows)
    if report["after_t"] or report["wrong_value"]:
        raise LeakError(f"未来の情報が混ざっています: {report}")
    if report["missing"] > max_missing:
        raise LeakError(f"特徴量が付かない行が {report['missing']} 行あります (上限 {max_missing}): {report}")
    return report
