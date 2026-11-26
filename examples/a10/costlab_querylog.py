"""クエリごとに読んだバイト数を記録し、誰が一番使っているかを順位にします。"""
import duckdb

from costlab_meter import measure


class QueryLog:
    def __init__(self):
        self.db = duckdb.connect()
        self.db.execute("CREATE TABLE log (tag VARCHAR, runs_per_day INTEGER, read_bytes BIGINT)")

    def record(self, con, tag, sql, runs_per_day):
        """測って、1 日の実行回数を掛けて 1 日分として記録します。"""
        m = measure(con, sql)
        self.db.execute("INSERT INTO log VALUES (?, ?, ?)", [tag, runs_per_day, m["read_bytes"]])
        return m

    def ranking(self):
        """タグごとの 1 日の読み取りバイト数と、全体に占める割合 (%) を大きい順に返します。"""
        return self.db.execute(
            "SELECT tag, sum(runs_per_day * read_bytes) AS bytes_per_day, "
            "round(100.0 * sum(runs_per_day * read_bytes) / sum(sum(runs_per_day * read_bytes)) OVER (), 1) AS share "
            "FROM log GROUP BY tag ORDER BY bytes_per_day DESC").fetchall()
