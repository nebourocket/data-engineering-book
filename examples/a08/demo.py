"""第8章の出力をまとめて出します (外部サービスは要りません)。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "a07"))
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))

import contract_check  # noqa: E402
import freshness_volume as fv  # noqa: E402
import lineage_events  # noqa: E402
import obs_case  # noqa: E402
import slo_burn  # noqa: E402


def show(title):
    print(f"--- {title}")


if __name__ == "__main__":
    log = fv.make_load_log()
    rows = [r["row_count"] for r in log]

    show("freshness")
    con = fv.load_into_duckdb(log)
    for d, finished in con.execute(fv.FRESHNESS_SQL).fetchall():
        print(f"{d} finished at {finished:%H:%M} (deadline 0{fv.DEADLINE_HOUR}:00)")

    show("volume naive")
    for k in (1.5, 2, 3):
        print(f"k={k}:", fv.score(fv.naive_flags(rows, k=k), 28))

    show("volume weekday")
    print("floor=0.2:", fv.score(fv.weekday_flags(rows), 28))
    print("floor=0  :", fv.score(fv.weekday_flags(rows, floor=0), 28))

    show("volume backfill")
    shifted = fv.with_backfill_and_late_data(rows)
    flagged = fv.weekday_flags(shifted)
    print("flagged days:", [i for i in flagged if i not in fv.INCIDENTS])
    print("with backfill day skipped:", [i for i in fv.weekday_flags(shifted, skip={fv.BACKFILL_DAY}) if i not in fv.INCIDENTS])
    print("rows on backfill day:", rows[fv.BACKFILL_DAY], "->", shifted[fv.BACKFILL_DAY])
    print("rows on late day and next:", (rows[fv.LATE_DAY], rows[fv.LATE_DAY + 1]), "->", (shifted[fv.LATE_DAY], shifted[fv.LATE_DAY + 1]))

    show("slo")
    for name, stalls in [("big", slo_burn.BIG), ("flapping", slo_burn.FLAPPING)]:
        bad = slo_burn.bad_flags(slo_burn.build_lag(stalls))
        print(f"{name}: bad samples {sum(bad)} of {len(bad)}, budget used {slo_burn.budget_used(bad):.1%}")
        for stall in stalls:
            print(f"  stall {stall}: bad samples and max lag (min) = {obs_case.bad_samples(stall)}")
    print("budget in samples: 30d", round(8640 * (1 - slo_burn.SLO), 1), "| 3d window", round(slo_burn.WINDOWS["3d"] * (1 - slo_burn.SLO), 1))

    show("alerts")
    for name, stalls in [("big", slo_burn.BIG), ("flapping", slo_burn.FLAPPING)]:
        print(name)
        for rule, (count, delays) in obs_case.run_alerts(stalls).items():
            print(f"  {rule}: fired {count} times, delay (min) {delays}")

    show("lineage event")
    events = lineage_events.one_night()
    print(json.dumps(events[1], ensure_ascii=False, indent=1))

    show("lineage impact")
    graph = lineage_events.build_graph(events)
    print(len(events), "events")
    for name in ("raw.orders", "raw.events", "mart.fact_sales"):
        print(name, "->", lineage_events.downstream(graph, name))
    print("raw.order_items ->", lineage_events.downstream(graph, "raw.order_items"))
    broken = lineage_events.one_night(failed_jobs=("build_fact_sales",))
    print("after FAIL of build_fact_sales, raw.orders ->", lineage_events.downstream(lineage_events.build_graph(broken), "raw.orders"))
    print("stale, behind stale:", lineage_events.stale_tables(broken))

    show("lineage drift")
    renamed = [(n, t) if n != "total_amount" else ("amount", t) for n, t in lineage_events.ORDERS_FIELDS]
    v1 = contract_check.load_schema("orders.v1.json")
    print("normal:", lineage_events.schema_drift(events, "raw.orders", v1))
    print("renamed:", lineage_events.schema_drift(lineage_events.one_night(orders_fields=renamed), "raw.orders", v1))

    show("case: monitor cost")
    for scale in (1, 100, 1000):
        n, days, sec = obs_case.daily_count_seconds(scale)
        print(f"{n} rows -> {days} daily counts in {sec:.4f} s (median of 5)")
