"""第5章の出力をまとめて出します。PG_DSN は共有の PostgreSQL、PG_LOGICAL_DSN は wal_level=logical のものです。"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))

import cdc_case_study  # noqa: E402
import consumers  # noqa: E402
import dwh_apply  # noqa: E402
import logical_demo  # noqa: E402
import outbox  # noqa: E402
import query_cdc  # noqa: E402
from sandbox import sandbox  # noqa: E402


def show(title, value):
    print(f"--- {title}")
    print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    pg, lg = os.environ["PG_DSN"], os.environ.get("PG_LOGICAL_DSN")
    with sandbox(pg) as box:
        show("query_cdc", query_cdc.run_scenario(box))
    with sandbox(pg) as box:
        show("outbox", outbox.compare(box))
    with sandbox(pg) as box:
        show("parallel relay", outbox.relay_in_parallel(box))
    with sandbox(pg) as box:
        show("state consumers", consumers.run_state_consumers(box))
        show("points consumers", consumers.run_points_consumers(box))
    show("styles", consumers.notification_vs_state([(7, "paid"), (7, "shipped"), (7, "delivered")]))
    for kw in [{}, {"replay_first": True}, {"shuffle_seed": 1}]:
        show(f"dwh {kw}", dwh_apply.run_dwh(**kw))
    if lg:
        lines, changes = logical_demo.wal_sees_everything(lg)
        show("test_decoding (末尾)", "\n".join(lines[-12:]))
        for full in (False, True):
            kinds, changes, envelopes, keys = logical_demo.pgoutput_events(lg, full)
            show(f"pgoutput full={full}", "".join(kinds))
            for c in changes:
                print(c)
            show(f"envelope full={full}", envelopes[1])
        show("slot keeps wal", logical_demo.slot_keeps_wal(lg))
        show("slot lost", logical_demo.slot_gets_lost(lg))
        for identity in ("DEFAULT", "FULL"):
            show(f"wal per update {identity}", cdc_case_study.wal_per_update(lg, identity))
        for n in (2000, 20000, 200000):
            show(f"case {n}", cdc_case_study.run(lg, n=n, updates=n * 3 // 100, deletes=n // 500, slow=max(1, n // 2000)))
