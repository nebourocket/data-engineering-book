"""指標の定義を一か所に置き、定義から SQL を作る小さなセマンティックレイヤー (DuckDB の SQL を出します)。"""

# 指標: 集計の式・条件・粒度。dbt の MetricFlow では YAML の semantic_models / metrics に当たります。
METRICS = {
    "gross_sales": {"grain": "line", "agg": "sum(i.quantity * i.unit_price)", "where": None,
                    "description": "キャンセルを含む売上 (マーケティングの見方)"},
    "net_sales": {"grain": "line", "agg": "sum(i.quantity * i.unit_price)", "where": "o.status <> 'cancelled'",
                  "description": "キャンセルを除く売上 (経理の見方)"},
    "shipped_sales": {"grain": "line", "agg": "sum(i.quantity * i.unit_price)",
                      "where": "o.status IN ('shipped', 'delivered')", "description": "出荷済みの売上 (物流の見方)"},
    "orders": {"grain": "order", "agg": "count(*)", "where": "o.status <> 'cancelled'",
               "description": "キャンセルを除く注文数"},
    "shipping_revenue": {"grain": "order", "agg": "sum(o.shipping_fee)", "where": "o.status <> 'cancelled'",
                         "description": "送料の合計 (注文単位)"},
}
# 比率の指標は、ほかの指標の名前で書きます
RATIOS = {"avg_order_value": ("net_sales", "orders")}
# 切り口: 式・必要な結合・使える粒度
DIMENSIONS = {
    "month": {"expr": "substr(o.ordered_at, 1, 7)", "joins": [], "grains": {"line", "order"}},
    "prefecture": {"expr": "c.prefecture", "joins": ["customer"], "grains": {"line", "order"}},
    "category": {"expr": "p.category", "joins": ["product"], "grains": {"line"}},
}
JOINS = {"customer": "JOIN customers c ON c.customer_id = o.customer_id",
         "product": "JOIN products p ON p.product_id = i.product_id"}
FROM = {"line": "orders o JOIN order_items i ON i.order_id = o.order_id", "order": "orders o"}


def compile_metric(name, by=(), where=None):
    """指標名と切り口から SQL を作ります。切り口が指標の粒度で使えないときは例外にします。"""
    if name in RATIOS:
        num, den = RATIOS[name]
        n, d = compile_metric(num, by, where), compile_metric(den, by, where)
        cols = ", ".join("n." + b for b in by)
        join_on = " AND ".join(f"n.{b} = d.{b}" for b in by) or "true"
        select = (f"SELECT {cols + ', ' if cols else ''}n.{num} / d.{den} AS {name} "
                  f"FROM ({n}) n JOIN ({d}) d ON {join_on}")
        return select + (f" ORDER BY {cols}" if cols else "")
    metric = METRICS[name]
    for b in by:
        if metric["grain"] not in DIMENSIONS[b]["grains"]:
            raise ValueError(f"切り口 {b} は、{metric['grain']} 粒度の指標 {name} には使えません")
    joins = sorted({j for b in by for j in DIMENSIONS[b]["joins"]})
    conditions = [c for c in (metric["where"], where) if c]
    sql = f"SELECT {''.join(DIMENSIONS[b]['expr'] + ' AS ' + b + ', ' for b in by)}{metric['agg']} AS {name}"
    sql += f" FROM {FROM[metric['grain']]}"
    sql += "".join(" " + JOINS[j] for j in joins if not (j == 'product' and metric['grain'] == 'order'))
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if by:
        sql += " GROUP BY ALL ORDER BY ALL"
    return sql


# 部署ごとに手で書いた「3 月の売上」。同じ名前なのに条件が違います
HAND_WRITTEN = {
    "経理": "SELECT sum(i.quantity * i.unit_price) FROM orders o JOIN order_items i USING (order_id) "
            "WHERE substr(o.ordered_at, 1, 7) = '2026-03' AND o.status <> 'cancelled'",
    "マーケティング": "SELECT sum(i.quantity * i.unit_price) FROM orders o JOIN order_items i USING (order_id) "
                "WHERE substr(o.ordered_at, 1, 7) = '2026-03'",
    "物流": "SELECT sum(i.quantity * i.unit_price) FROM orders o JOIN order_items i USING (order_id) "
          "WHERE substr(o.ordered_at, 1, 7) = '2026-03' AND o.status IN ('shipped', 'delivered')",
}
