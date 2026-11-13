"""品質チェック (第13章の仕組みを、この演習に必要な分だけ小さくした版です)。

確認は「悪い行の数 bad」と「見た行の数 total」を返す SQL 1 本です。bad / total が max_ratio 以下なら合格。
不合格のとき、severity が "error" なら QualityError で止め、"warn" なら記録して先へ進みます。
SQL はこのファイルに書いた値だけから作ります (利用者の入力を埋めると SQL インジェクションになります)。
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Check:
    name: str
    severity: str  # "error" か "warn"
    sql: str  # (bad, total) を返す SELECT
    max_ratio: float = 0.0


class QualityError(Exception):
    """severity が error の確認が不合格だったときに投げます。"""


CHECKS = [
    Check("orders が空でない", "error",
          "SELECT CASE WHEN count(*) > 0 THEN 0 ELSE 1 END, 1 FROM main.orders"),
    Check("日別売上の日付が NULL でも重複でもない", "error",
          "SELECT count(*) FILTER (WHERE order_date IS NULL) + count(*) - count(DISTINCT order_date), "
          "count(*) FROM analytics.fct_daily_sales"),
    Check("日別売上の合計が raw の明細と一致する", "error",
          """SELECT CASE WHEN
                 (SELECT sum(sales) FROM analytics.fct_daily_sales) =
                 (SELECT sum(i.quantity * i.unit_price)
                    FROM main.order_items AS i JOIN main.orders AS o USING (order_id)
                   WHERE lower(o.status) <> 'cancelled')
             THEN 0 ELSE 1 END, 1"""),
    Check("events の event_id が重複していない", "warn",
          "SELECT count(*) - count(DISTINCT event_id), count(*) FROM main.events"),
    Check("events の遅延到着 (翌日以降) が 5% 以下", "warn",
          "SELECT count(*) FILTER (WHERE CAST(received_at AS TIMESTAMP) - CAST(event_time AS TIMESTAMP) "
          ">= INTERVAL 1 DAY), count(*) FROM main.events", 0.05),
]


def run_checks(con, run_dt, checks=CHECKS):
    """全部の確認を実行して dq_results に残します。error が 1 つでも不合格なら、残したあとで止めます。"""
    con.execute("""CREATE TABLE IF NOT EXISTS dq_results (
        run_dt VARCHAR, check_name VARCHAR, severity VARCHAR, bad BIGINT, total BIGINT,
        passed BOOLEAN, checked_at TIMESTAMPTZ)""")
    con.execute("DELETE FROM dq_results WHERE run_dt = ?", [run_dt])  # 同じ日を再実行しても結果は 1 組だけ
    failed = []
    for check in checks:
        bad, total = con.execute(check.sql).fetchone()
        passed = total == 0 or bad / total <= check.max_ratio
        con.execute("INSERT INTO dq_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [run_dt, check.name, check.severity, bad, total, passed, datetime.now(timezone.utc)])
        if not passed and check.severity == "error":
            failed.append(check.name)
    if failed:
        raise QualityError("error の確認が不合格です: " + ", ".join(failed))
