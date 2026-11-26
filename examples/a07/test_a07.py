"""第7章のコードの検査。合否・件数・規則と実データの一致を確かめます (秒数は見ません)。"""
import copy

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

import contract_case
import contract_check
import schema_evolution
import semantic_rules
from neboske_shop import generate

V1 = contract_check.load_schema("orders.v1.json")
V2 = contract_check.load_schema("orders.v2.json")


@pytest.fixture(scope="module")
def orders():
    return contract_check.shop_orders()


def test_contract_document_is_complete():
    contract = contract_check.load_contract()
    assert contract["schema"] == "orders.v1.json"
    assert contract["compatibility"] == "backward"


def test_real_shop_data_breaks_the_contract(orders):
    violations = contract_check.validate_batch(V1, orders)
    assert len(violations) == 59 and {v["path"] for v in violations} == {"status"}
    assert contract_check.ci_gate(V1, orders) == 1
    assert contract_check.ci_gate(V1, orders, max_bad_rate=0.02) == 0  # 1.97% は 2% の上限に収まる
    cleaned = [o for o in orders if o["status"] != "SHIPPED"]
    assert contract_check.ci_gate(V1, cleaned) == 0


def test_bad_schema_is_rejected_before_use():
    with pytest.raises(SchemaError):
        Draft202012Validator.check_schema({"type": "no-such-type"})


def test_adding_optional_field_is_backward_but_not_forward_in_closed_model():
    result = schema_evolution.check(V1, V2)
    assert result["backward"] == [] and result["forward"] != []
    assert schema_evolution.evolution_gate(V1, V2, "backward") == 0
    assert schema_evolution.evolution_gate(V1, V2, "forward") == 1
    assert schema_evolution.evolution_gate(V1, V2, "full") == 1


@pytest.mark.parametrize("open_model", [False, True])
def test_rule_never_says_ok_when_real_data_disagrees(open_model):
    rows = schema_evolution.run_scenarios(V1, open_model)
    assert len(rows) == 9
    for name, rule, data in rows:
        for mode in ("backward", "forward"):
            assert not rule[mode] or data[mode], f"{name}: 規則は OK なのに実データで拒否された ({mode})"


def test_rule_can_be_stricter_than_samples():
    # 開いた形では、実データに現れない値の型までは分からないので、規則だけが NG と言う
    rows = {name: (rule, data) for name, rule, data in schema_evolution.run_scenarios(V1, True)}
    rule, data = rows["任意の列 coupon_code を足す"]
    assert rule["backward"] is False and data["backward"] is True


def test_rename_is_breaking_in_both_directions():
    new = contract_case.renamed_schema(V1)
    assert schema_evolution.check(V1, new)["backward"] and schema_evolution.check(V1, new)["forward"]
    assert schema_evolution.evolution_gate(V1, new, "backward") == 1


def test_prop_within_basics():
    assert schema_evolution.prop_within({"type": "integer"}, {"type": "number"})
    assert not schema_evolution.prop_within({"type": "number"}, {"type": "integer"})
    assert schema_evolution.prop_within({"enum": ["a"]}, {"enum": ["a", "b"]})
    assert not schema_evolution.prop_within({"type": "integer"}, {"type": "integer", "minimum": 0})
    assert schema_evolution.prop_within({"type": "integer", "minimum": 1}, {"type": "integer", "minimum": 0})


def test_semantic_rules_find_what_json_schema_cannot(orders):
    shop = generate()
    clean = semantic_rules.load_tables(orders, shop["order_items"], shop["customers"])
    assert set(semantic_rules.run_rules(clean).values()) == {0}
    typed_ok = [o for o in orders if o["status"] != "SHIPPED"]
    broken_orders = contract_case.inject_defects(typed_ok)
    assert contract_check.validate_batch(V1, broken_orders) == []  # 型の検査は全部通る
    broken = semantic_rules.load_tables(broken_orders, shop["order_items"], shop["customers"])
    assert list(semantic_rules.run_rules(broken).values()) == [30, 12, 5]


def test_silent_rename_zeroes_revenue_but_contract_catches_it(orders):
    released = contract_case.rename_release(orders)
    rows = contract_case.monthly_revenue_from_docs(released)
    before = dict((m, r) for m, _, _, r in contract_case.monthly_revenue_from_docs(orders))
    after = {m: (n, w, r) for m, n, w, r in rows}
    assert after["2026-03"][2] == before["2026-03"]
    assert after["2026-04"] == (847, 0, None)
    accepted, quarantine = contract_case.ingest_with_contract(V1, released)
    assert len(accepted) + len(quarantine) == 3000
    assert len(accepted) == 1451 and len(quarantine) == 1549
    assert len(contract_case.ingest_with_contract(V1, orders)[0]) == 2941  # 3000 - SHIPPED の 59
    after_release = [o for o in orders if o["ordered_at"] >= contract_case.RELEASE_DAY]
    shipped_before = [o for o in orders if o["ordered_at"] < contract_case.RELEASE_DAY and o["status"] == "SHIPPED"]
    assert (len(after_release), len(shipped_before), len(quarantine)) == (1520, 29, 1549)


def test_expand_then_contract_needs_a_human():
    expanded = contract_case.expanded_schema(V1)
    assert schema_evolution.evolution_gate(V1, expanded, "backward") == 0
    assert schema_evolution.evolution_gate(expanded, contract_case.contracted_schema(expanded), "backward") == 1


EXPECTED = {  # 名前 -> (規則 後方, 規則 前方, 実データ 後方, 実データ 前方)
    False: [(True, False, True, False), (False, False, False, False), (False, True, False, True),
            (True, False, True, False), (False, True, False, True), (True, False, True, False),
            (False, False, False, False), (True, False, True, False), (False, True, False, True)],
    True: [(False, True, True, True), (False, True, False, True), (True, False, True, True),
           (True, False, True, False), (False, True, False, True), (True, False, True, False),
           (False, False, False, False), (True, False, True, False), (False, True, False, True)],
}


@pytest.mark.parametrize("open_model", [False, True])
def test_nine_scenarios_match_the_printed_table(open_model):
    got = [(r["backward"], r["forward"], d["backward"], d["forward"])
           for _, r, d in schema_evolution.run_scenarios(V1, open_model)]
    assert got == EXPECTED[open_model]


@pytest.mark.parametrize("keyword,value", [("maxLength", 5), ("exclusiveMinimum", 5), ("multipleOf", 10)])
def test_gate_fails_closed_on_unsupported_keywords(keyword, value, capsys):
    new = copy.deepcopy(V1)
    new["properties"]["total_amount"][keyword] = value
    assert schema_evolution.evolution_gate(V1, new, "backward") == 1
    assert f"未対応のキーワード {keyword}" in capsys.readouterr().out


def test_gate_fails_closed_when_pattern_changes_but_not_when_unchanged():
    new = copy.deepcopy(V1)
    new["properties"]["ordered_at"]["pattern"] = "^2026"
    assert schema_evolution.unchecked(V1, new) == ["ordered_at の未対応のキーワード pattern が変わった"]
    assert schema_evolution.unchecked(V1, V2) == []


def test_empty_batch_is_rejected_not_passed():
    with pytest.raises(ValueError):
        contract_check.ci_gate(V1, [])


def test_format_is_not_asserted_by_default():
    ipv4 = {"type": "string", "format": "ipv4"}
    assert Draft202012Validator(ipv4).is_valid("not an address")
    assert not Draft202012Validator(ipv4, format_checker=Draft202012Validator.FORMAT_CHECKER).is_valid("not an address")
    # date-time は、フォーマット検査を渡しても追加のパッケージが無いと検査されない (この環境の結果)
    dt = {"type": "string", "format": "date-time"}
    assert Draft202012Validator(dt, format_checker=Draft202012Validator.FORMAT_CHECKER).is_valid("not a date")


def test_quarantine_repair_and_replay_restores_everything_once(orders):
    released = contract_case.rename_release(orders)
    accepted, _ = contract_case.ingest_with_contract(V1, released)
    rejected = contract_case.rejected_docs(V1, released)
    merged, still_bad = contract_case.replay(V1, accepted, rejected)
    assert (len(rejected), len(still_bad), len(merged)) == (1549, 0, 3000)
    assert sum(d["total_amount"] for d in merged) == sum(o["total_amount"] for o in orders) == 41665750
    assert len(contract_case.replay(V1, merged, rejected)[0]) == 3000  # 2 回流しても増えない


def test_staged_rollout(orders):
    assert contract_case.staged_gate(V1, orders, "warn") == 0
    assert contract_case.staged_gate(V1, orders, "block") == 1
    assert contract_case.staged_gate(V1, [contract_case.repair(o) for o in orders], "block") == 0


def test_required_bump():
    strict = copy.deepcopy(V1)
    strict["properties"]["ordered_at"]["maxLength"] = 19
    got = [schema_evolution.required_bump(V1, new, "backward")
           for new in (V2, contract_case.renamed_schema(V1), strict, copy.deepcopy(V1))]
    assert got == ["minor", "major", "review", "patch"]


def test_gate_fails_closed_on_top_level_type_and_schema_valued_additional_properties():
    new = copy.deepcopy(V1)
    new["type"] = "array"
    assert schema_evolution.unchecked(V1, new) == ["未対応のキーワード type (スキーマ全体) が変わった"]
    loose, other = copy.deepcopy(V1), copy.deepcopy(V1)
    loose["additionalProperties"] = {"type": "string"}
    other["additionalProperties"] = {"type": "integer"}
    assert len(schema_evolution.unchecked(loose, other)) == 1
    assert schema_evolution.evolution_gate(loose, other, "backward") == 1
    assert schema_evolution.unchecked(V1, V2) == []
