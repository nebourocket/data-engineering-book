"""絞る列が 2 つあるとき、並べ替えは 1 つの列にしか効きません。"""
from costlab_meter import measure


def two_column_report(con, root):
    """日付順と顧客番号順の 2 ファイルで、日付の絞り込みと顧客番号の絞り込みの読み取りバイトを測ります。"""
    con.execute(f"COPY (SELECT * FROM events ORDER BY customer_id) TO '{root}/by_customer.parquet' "
                "(FORMAT parquet, ROW_GROUP_SIZE 50000)")
    by_date = f"read_parquet('{root}/sorted.parquet')"
    by_customer = f"read_parquet('{root}/by_customer.parquet')"
    date_filter = "event_date BETWEEN '2026-03-01' AND '2026-03-07'"
    customer_filter = "customer_id BETWEEN 1 AND 500"
    return {(name, label): measure(con, f"SELECT sum(amount) FROM {src} WHERE {cond}")["read_bytes"]
            for name, src in (("日付順", by_date), ("顧客番号順", by_customer))
            for label, cond in (("日付で絞る", date_filter), ("顧客番号で絞る", customer_filter))}
