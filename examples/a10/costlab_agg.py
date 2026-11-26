"""事前集計: 集計表を 1 度だけ作り、ダッシュボードは集計表を読みます。"""
from costlab_case import workload
from costlab_meter import measure


def build_daily_agg(con, root):
    """日付・イベント種別ごとの合計と件数を、日付順の 1 ファイルに書きます。"""
    path = f"{root}/daily_agg.parquet"
    con.execute("COPY (SELECT event_date, event_type, sum(amount) AS amount, count(*) AS n FROM events "
                f"GROUP BY ALL ORDER BY event_date) TO '{path}' (FORMAT parquet)")
    return path


def dashboard_bytes(con, raw_src, agg_path):
    """ダッシュボードの 1 回の読み取りバイト数を、元の表と集計表で比べます。"""
    raw_sql = workload(raw_src)[0][1]
    agg_sql = ("SELECT event_type, sum(amount) FROM read_parquet('" + agg_path + "') "
               "WHERE event_date BETWEEN '2026-03-01' AND '2026-03-07' GROUP BY event_type")
    return measure(con, raw_sql)["read_bytes"], measure(con, agg_sql)["read_bytes"]
