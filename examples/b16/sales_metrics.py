"""第16章: 「売上」の定義がずれる様子と、定義を 1 か所に置く縮小版の指標層。"""
import duckdb

# 同じ fct_orders から、3 人が別々に「売上」を出したときの式です。
SALES_DEFINITIONS = {
    "全注文": "sum(order_amount)",
    "キャンセル除く": "sum(order_amount) filter (where status <> 'cancelled')",
    "配達済みのみ": "sum(order_amount) filter (where status = 'delivered')",
}

# 指標層の縮小版: 指標と切り口の定義を、ここだけに書きます。
METRICS = {
    "sales": "sum(order_amount) filter (where status <> 'cancelled')",
    "orders": "count(*) filter (where status <> 'cancelled')",
}
DIMENSIONS = {
    "month": "strftime(ordered_at, '%Y-%m')",
    "day": "cast(ordered_at as date)",
}


def metric_sql(metric: str, dimension: str) -> str:
    """指標と切り口の名前から SQL を作ります。未定義の名前は KeyError で止めます。"""
    return (
        f"select {DIMENSIONS[dimension]} as {dimension}, {METRICS[metric]} as {metric} "
        f"from fct_orders group by 1 order by 1"
    )


def monthly_by_definition(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """月ごとの売上を、3 つの定義で並べます。"""
    columns = ", ".join(f"{expr} as \"{name}\"" for name, expr in SALES_DEFINITIONS.items())
    return con.execute(
        f"select strftime(ordered_at, '%Y-%m') as month, {columns} from fct_orders group by 1 order by 1"
    ).fetchall()
