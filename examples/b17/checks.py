"""この演習の品質確認の一覧。仕組み (Check・gate・dq_results) は第13章の examples/b13/quality.py をそのまま使います。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "b13"))  # 第13章のコードは、フォルダの中の名前で読み込む
import quality as dq  # noqa: E402  (第13章)

MART = "analytics.fct_daily_sales"  # 第10章の dbt が作る日別売上


def sales_checks():
    """error は売上の数字そのものが壊れるもの、warn は売上に直接使わない events の欠陥です。"""
    return [
        dq.row_count_between("main.orders", 1, 10_000_000),  # orders が空でない
        dq.not_null(MART, "order_date"),
        dq.unique(MART, "order_date"),
        # 売上の突合 (2 つの出どころの数字が合うか): mart の合計と、raw の明細から数え直した合計
        dq.Check("日別売上の合計が raw の明細と一致する", "整合性", "error", """
            SELECT CASE WHEN
                (SELECT sum(sales) FROM analytics.fct_daily_sales) =
                (SELECT sum(i.quantity * i.unit_price)
                   FROM main.order_items AS i JOIN main.orders AS o USING (order_id)
                  WHERE lower(o.status) <> 'cancelled')
            THEN 0 ELSE 1 END, 1"""),
        dq.unique("main.events", "event_id", severity="warn"),  # 重複して届いた events (元データの既知の欠陥)
        dq.late_arrival("main.events", "event_time", "received_at", 0.05),  # 翌日以降に届いた割合が 5% 以下
    ]
