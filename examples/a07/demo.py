"""第7章の出力をまとめて出します (外部サービスは要りません)。"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))

import contract_case  # noqa: E402
import contract_check  # noqa: E402
import schema_evolution  # noqa: E402
import semantic_rules  # noqa: E402
from neboske_shop import generate  # noqa: E402


def show(title):
    print(f"--- {title}")


def mark(ok):
    return "OK" if ok else "NG"


def scenario_table(old, open_model):
    for name, rule, data in schema_evolution.run_scenarios(old, open_model):
        full = rule["backward"] and rule["forward"]
        print(f"{name}: 規則 後方={mark(rule['backward'])} 前方={mark(rule['forward'])} 双方={mark(full)}"
              f" / 実データ 後方={mark(data['backward'])} 前方={mark(data['forward'])}")


if __name__ == "__main__":
    v1 = contract_check.load_schema("orders.v1.json")
    v2 = contract_check.load_schema("orders.v2.json")
    orders = contract_check.shop_orders()
    shop = generate()

    show("contract")
    contract = contract_check.load_contract()
    print(contract["name"], contract["version"], contract["compatibility"], contract["sla"])

    show("ci gate on shop data")
    violations = contract_check.validate_batch(v1, orders)
    print(len(violations), violations[0])
    print("exit code:", contract_check.ci_gate(v1, orders))
    print("exit code with limit 0.02:", contract_check.ci_gate(v1, orders, max_bad_rate=0.02))

    show("evolution gate v1 -> v2")
    print("exit code:", schema_evolution.evolution_gate(v1, v2, "backward"))
    print("exit code:", schema_evolution.evolution_gate(v1, v2, "full"))

    show("unsupported keyword")
    strict = copy.deepcopy(v1)
    strict["properties"]["total_amount"]["maxLength"] = 9
    print("exit code:", schema_evolution.evolution_gate(v1, strict, "backward"))
    changed = copy.deepcopy(v1)
    changed["properties"]["ordered_at"]["pattern"] = "^2026"
    print("exit code:", schema_evolution.evolution_gate(v1, changed, "backward"))

    show("scenarios (closed schema)")
    scenario_table(v1, False)
    show("scenarios (open schema)")
    scenario_table(v1, True)

    show("semantic rules")
    clean = semantic_rules.load_tables(orders, shop["order_items"], shop["customers"])
    print("clean:", semantic_rules.run_rules(clean))
    typed_ok = [o for o in orders if o["status"] != "SHIPPED"]
    broken_orders = contract_case.inject_defects(typed_ok)
    print("JSON Schema violations in broken orders:", len(contract_check.validate_batch(v1, broken_orders)))
    broken = semantic_rules.load_tables(broken_orders, shop["order_items"], shop["customers"])
    print("broken:", semantic_rules.run_rules(broken))

    show("case: silent rename")
    released = contract_case.rename_release(orders)
    print("month, orders, orders_with_amount, revenue")
    for label, docs in [("before", orders), ("after", released)]:
        for row in contract_case.monthly_revenue_from_docs(docs):
            print(label, *row)

    show("case: producer ci gate")
    print("exit code:", schema_evolution.evolution_gate(v1, contract_case.renamed_schema(v1), "backward"))

    show("expand and contract")
    expanded = contract_case.expanded_schema(v1)
    print("expand step:")
    print("exit code:", schema_evolution.evolution_gate(v1, expanded, "backward"))
    print("contract step:")
    print("exit code:", schema_evolution.evolution_gate(expanded, contract_case.contracted_schema(expanded), "backward"))

    show("case: quarantine")
    accepted, quarantine = contract_case.ingest_with_contract(v1, released)
    print("accepted", len(accepted), "quarantined", len(quarantine))
    print(quarantine[0])

    show("repair and replay")
    rejected = contract_case.rejected_docs(v1, released)
    merged, still_bad = contract_case.replay(v1, accepted, rejected)
    merged_again, _ = contract_case.replay(v1, merged, rejected)
    total = lambda docs: sum(d["total_amount"] for d in docs)  # noqa: E731
    print("rejected", len(rejected), "still bad", len(still_bad))
    print("after replay", len(merged), "orders, revenue", total(merged), "(original", total(orders), ")")
    print("replayed twice", len(merged_again), "orders")

    show("rollout stages")
    print("warn exit code:", contract_case.staged_gate(v1, orders, "warn"))
    print("block exit code:", contract_case.staged_gate(v1, orders, "block"))
    print("block after repair exit code:", contract_case.staged_gate(v1, [contract_case.repair(o) for o in orders], "block"))

    show("version bump")
    renamed = contract_case.renamed_schema(v1)
    strict = copy.deepcopy(v1)
    strict["properties"]["ordered_at"]["maxLength"] = 19
    for label, new in [("add optional column", v2), ("rename", renamed), ("add maxLength", strict), ("no change", copy.deepcopy(v1))]:
        print(f"{label}: {schema_evolution.required_bump(v1, new, 'backward')}")

    show("case: validation speed")
    for repeat in (1, 10):
        n, rate = contract_case.validation_rate(v1, orders, repeat)
        print(f"validated {n} records at about {round(rate, -4):,.0f} records/s")
