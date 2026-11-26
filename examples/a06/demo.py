"""第6章の出力をまとめて出します (DuckDB だけで動きます)。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

sys.path.insert(0, str(Path(__file__).parent.parent / "common"))

import aggregates  # noqa: E402
import model_case_study as case_study  # noqa: E402
import conformed  # noqa: E402
import datavault  # noqa: E402
import grain  # noqa: E402
import late_dim  # noqa: E402
import migrate  # noqa: E402
import mini_dim  # noqa: E402
import models  # noqa: E402
import semantic  # noqa: E402


def show(title, value):
    print(f"--- {title}")
    print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    con = models.load_source(10)
    models.build_star(con)
    models.build_obt(con)
    a, b = models.load_source(1), models.load_source(1)
    for con2 in (a, b):
        datavault.create_vault(con2)
    tables = ["hub_order", "link_order_line", "sat_order_line", "sat_customer"]
    order_a, order_b = datavault.load_all(a), datavault.load_all(b, seed=5)
    show("vault order", {"order_a": order_a, "order_b": order_b,
                         "same_content": datavault.digest(a, tables) == datavault.digest(b, tables),
                         "rows": datavault.digest(a, tables)})
    show("grain", grain.shipping_by_method(con))
    show("aov", grain.average_order_value(con))
    show("late dimension", late_dim.demo())
    show("mini dimension", mini_dim.simulate())
    big = models.load_source(100)
    models.build_star(big)
    models.build_obt(big)
    show("profile key cost (100x)", mini_dim.profile_key_cost(big))
    show("late dimension (vault)", late_dim.vault_demo())
    show("conformed", conformed.non_conformed_demo())
    show("select star breaks", conformed.adding_a_column_breaks_select_star())
    show("partition and cluster (100x)", aggregates.partition_and_cluster(big))
    big.execute(aggregates.AGG_SQL)
    show("aggregate (100x)", aggregates.aggregate_scan(big))
    show("star scd2 move", case_study.star_scd2_move(10))
    show("vault view joins", case_study.vault_view_joins())
    show("hash collision", datavault.hash_collision_example(one_con := models.load_source(1)))
    show("migrate ok", migrate.migrate(models.load_source(1)))
    show("migrate buggy", migrate.migrate(models.load_source(1), migrate.SALES_V2_BUGGY))
    one = models.load_source(1)
    show("hand written March", {k: one.execute(v).fetchone()[0] for k, v in semantic.HAND_WRITTEN.items()})
    march = "substr(o.ordered_at, 1, 7) = '2026-03'"
    show("compiled March", {m: one.execute(semantic.compile_metric(m, (), march)).fetchone()[0]
                            for m in ("net_sales", "gross_sales", "shipped_sales")})
    show("sql", semantic.compile_metric("net_sales", ["month", "category"]))
    show("sql ratio", semantic.compile_metric("avg_order_value", ["prefecture"]))
    for scale in (1, 10, 100):
        show(f"measure {scale}", case_study.measure(scale))
        show(f"changes {scale}", case_study.measure_changes(scale))
        show(f"vault flavors {scale}", case_study.measure_vault_flavors(scale))
