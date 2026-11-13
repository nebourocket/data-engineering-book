"""データ品質の確認を実行し、結果を表（dq_results）に残す小さな実行器です。

確認（Check）は「悪い行の数 bad」と「見た行の数 total」を返す SQL 1 本で表します。
bad / total が max_ratio 以下なら合格です。不合格のとき、severity が
  "error" なら QualityError を投げて処理を止め、"warn" なら通知だけして先へ進み、
  "info" なら結果を表に残すだけで通知もしません (傾向を見たい確認用)。
SQL に埋める表名と列名は、このファイルに書いた信頼できる値だけを渡してください
（利用者の入力を渡すと SQL インジェクションになります）。DuckDB で動かします。
"""
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import write_duckdb  # noqa: E402


@dataclass(frozen=True)
class Check:
    name: str
    dimension: str  # 完全性・一意性・鮮度など
    severity: str  # "error" か "warn" か "info"
    sql: str  # 1 行 2 列 (bad, total) を返す SELECT
    max_ratio: float = 0.0
    owner: str = ""  # 通知に添える持ち主 (チーム名など)


class QualityError(Exception):
    """severity が error の確認が不合格だったときに投げます。"""


def not_null(table, column, severity="error", max_ratio=0.0):
    return Check(f"{table}.{column}_not_null", "完全性", severity,
                 f"SELECT count(*) FILTER (WHERE {column} IS NULL), count(*) FROM {table}", max_ratio)


def unique(table, column, severity="error", max_ratio=0.0):
    # NULL は一意性ではなく完全性の話なので数えない。bad は「余分な行数」。
    return Check(f"{table}.{column}_unique", "一意性", severity,
                 f"SELECT count(*) - count(DISTINCT {column}), count(*) FROM {table} "
                 f"WHERE {column} IS NOT NULL", max_ratio)


def accepted_values(table, column, values, severity="error", max_ratio=0.0):
    # 値に ' が含まれると SQL が壊れるので '' に直す (値もコードに書いた信頼できるものだけを渡す)
    listed = ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)
    return Check(f"{table}.{column}_accepted_values", "正確さ", severity,
                 f"SELECT count(*) FILTER (WHERE {column} NOT IN ({listed})), count(*) FROM {table} "
                 f"WHERE {column} IS NOT NULL", max_ratio)


def relationships(table, column, ref_table, ref_column, severity="error"):
    return Check(f"{table}.{column}_in_{ref_table}", "参照整合性", severity,
                 f"SELECT count(*) FILTER (WHERE r.{ref_column} IS NULL), count(*) "
                 f"FROM {table} AS t LEFT JOIN {ref_table} AS r ON t.{column} = r.{ref_column} "
                 f"WHERE t.{column} IS NOT NULL")


def freshness(table, column, max_lag_hours, as_of, severity="error"):
    # as_of は「今」の代わりに渡す時刻 (UTC)。date_diff は DuckDB の関数 (PostgreSQL では書き方が違う)。
    return Check(f"{table}.{column}_freshness", "鮮度", severity,
                 f"SELECT CASE WHEN date_diff('hour', CAST(max({column}) AS TIMESTAMP), "
                 f"TIMESTAMP '{as_of}') > {max_lag_hours} THEN 1 ELSE 0 END, 1 FROM {table}")


def row_count_between(table, low, high, severity="error"):
    return Check(f"{table}_row_count", "量", severity,
                 f"SELECT CASE WHEN count(*) BETWEEN {low} AND {high} THEN 0 ELSE 1 END, 1 FROM {table}")


def late_arrival(table, event_col, received_col, max_ratio, severity="warn"):
    # 受信が発生の 1 日以上後なら遅れた行。文字列の日時なので TIMESTAMP に直して引く。
    return Check(f"{table}_late_arrival", "鮮度", severity,
                 f"SELECT count(*) FILTER (WHERE CAST({received_col} AS TIMESTAMP) - "
                 f"CAST({event_col} AS TIMESTAMP) >= INTERVAL 1 DAY), count(*) FROM {table}", max_ratio)


def volume_zscore(table, column, day, z_max=3.0, severity="warn"):
    # day の件数が、直前 28 日の日別件数の平均から標準偏差 z_max 個分以上離れていれば bad。
    # 基準が作れない (標準偏差が NULL か 0) ときも bad にする。測れないものを合格にしない。
    return Check(f"{table}_volume_zscore", "分布", severity, f"""
        WITH daily AS (SELECT CAST({column} AS DATE) AS d, count(*) AS n FROM {table} GROUP BY d),
        base AS (SELECT avg(n) AS mu, NULLIF(stddev_samp(n), 0) AS sd FROM daily
                 WHERE d >= DATE '{day}' - 28 AND d < DATE '{day}'),
        today AS (SELECT coalesce(max(n), 0) AS n FROM daily WHERE d = DATE '{day}')
        SELECT CASE WHEN base.sd IS NULL OR abs((today.n - base.mu) / base.sd) > {z_max}
                    THEN 1 ELSE 0 END, 1
        FROM today, base""")


def quarantine_ratio(quarantine_table, source_table, max_ratio, severity="warn"):
    # 隔離した行が元の行の何割か。急に増えたら、上流で何かが起きている。
    return Check(f"{quarantine_table}_ratio", "完全性", severity,
                 f"SELECT (SELECT count(*) FROM {quarantine_table}), (SELECT count(*) FROM {source_table})",
                 max_ratio)


def schema_matches(table, expected, severity="error", schema="main"):
    # expected は {列名: 型名}。足りない列・型の違う列・余計な列の数が bad。
    pairs = ", ".join(f"('{c}', '{t}')" for c, t in expected.items())
    return Check(f"{table}_schema", "スキーマ", severity, f"""
        WITH want(column_name, data_type) AS (VALUES {pairs}),
        have AS (SELECT column_name, data_type FROM information_schema.columns
                 WHERE table_name = '{table}' AND table_schema = '{schema}')
        SELECT (SELECT count(*) FROM want WHERE (column_name, data_type) NOT IN
                    (SELECT column_name, data_type FROM have))
             + (SELECT count(*) FROM have WHERE column_name NOT IN
                    (SELECT column_name FROM want)), {len(expected)}""")


@dataclass(frozen=True)
class Result:
    check: Check
    bad: int
    total: int
    passed: bool
    detail: str = ""

    @property
    def ratio(self):
        return self.bad / self.total if self.total else 0.0


def _evaluate(con, check):
    try:
        bad, total = con.execute(check.sql).fetchone()
    except duckdb.Error as e:  # 測れなかった確認は不合格にする
        return Result(check, 0, 0, False, f"{type(e).__name__}: {str(e).splitlines()[0]}")
    return Result(check, bad, total, (bad / total if total else 0.0) <= check.max_ratio)


def run_checks(con, checks, run_id, now=None):
    """全部の確認を流し、結果を dq_results に追記して list[Result] を返します。"""
    now = now or datetime.now(timezone.utc)
    con.execute("""
        CREATE TABLE IF NOT EXISTS dq_results (
            run_id VARCHAR, run_at TIMESTAMPTZ, check_name VARCHAR, dimension VARCHAR,
            severity VARCHAR, owner VARCHAR, bad BIGINT, total BIGINT, ratio DOUBLE, max_ratio DOUBLE,
            passed BOOLEAN, detail VARCHAR)""")
    results = [_evaluate(con, c) for c in checks]
    for r in results:
        con.execute("INSERT INTO dq_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [run_id, now, r.check.name, r.check.dimension, r.check.severity,
                     r.check.owner, r.bad, r.total, r.ratio, r.check.max_ratio, r.passed, r.detail])
    return results


def gate(con, checks, run_id, notify=print, now=None):
    """確認を流し、warn の不合格は notify で知らせ、error の不合格があれば止めます。"""
    results = run_checks(con, checks, run_id, now)
    failed = [r for r in results if not r.passed]
    for r in failed:
        if r.check.severity == "warn":
            owner = f" (持ち主: {r.check.owner})" if r.check.owner else ""
            notify(f"[WARN] {r.check.name}: {r.bad}/{r.total} {r.detail}{owner}".rstrip())
    errors = [r for r in failed if r.check.severity == "error"]
    if errors:
        names = ", ".join(r.check.name for r in errors)
        raise QualityError(f"品質確認で止めました: {names}")
    return results


def shop_checks(table_suffix="", as_of="2026-07-02 00:00:00", day="2026-06-20", rows=(3500, 4500)):
    """ねぼすけ商店の確認一覧。table_suffix="_clean" で隔離後の events を確かめます。

    as_of (鮮度の「今」)・day (件数の Z スコアを見る日)・rows (件数の範囲) は、サンプルデータに
    合わせた値です。本番では実行日の時刻と日付を渡し、範囲は過去の実績から決めます。
    """
    ev = f"events{table_suffix}"
    extra = [quarantine_ratio("events_quarantine", "events", max_ratio=0.02)] if table_suffix else []
    return extra + [
        not_null("customers", "customer_id"),
        not_null("customers", "email", severity="warn", max_ratio=0.02),
        unique("customers", "email", severity="warn"),
        unique("orders", "order_id"),
        accepted_values("orders", "status", ["placed", "shipped", "delivered", "cancelled"],
                        severity="warn"),
        relationships("orders", "customer_id", "customers", "customer_id"),
        relationships("order_items", "product_id", "products", "product_id"),
        unique(ev, "event_id"),
        freshness(ev, "received_at", max_lag_hours=48, as_of=as_of),
        late_arrival(ev, "event_time", "received_at", max_ratio=0.05, severity="info"),
        row_count_between(ev, *rows),
        volume_zscore(ev, "event_time", day=day),
        schema_matches("customers", {"customer_id": "BIGINT", "name": "VARCHAR", "email": "VARCHAR",
                                     "prefecture": "VARCHAR", "registered_at": "VARCHAR"}),
    ]


def main(db="shop.duckdb", run_id=None):
    """終了コード 0 = 先へ進んでよい、1 = error の不合格あり (cron や Airflow が止められる)。"""
    path = Path(db)
    if not path.exists():
        write_duckdb(path)
    con = duckdb.connect(str(path))
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        results = gate(con, shop_checks(), run_id)
    except QualityError as e:
        print(e)
        return 1
    finally:
        con.close()
    print(f"全 {len(results)} 件の確認を通りました (warn の不合格は上に表示)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:2]))
