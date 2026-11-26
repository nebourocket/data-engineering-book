"""第12章のコードの検査。台帳の穴の検出・雛形の拒否・待ち行列の数字・設計レビューの検査を確かめます。"""
import copy
from pathlib import Path

import pytest

import design_review
import domain_registry as dr
import golden_path
import queue_sim
import tco

HERE = Path(__file__).parent


@pytest.fixture
def clean():
    """穴の無い小さな台帳 (変異させて、検査が穴を見つけるかを確かめる土台)。"""
    return {
        "teams": {"a-team": {"domain": "a", "on_call": True}, "b-team": {"domain": "b", "on_call": True}},
        "products": {
            "raw.x": {"domain": "a", "owner": "a-team", "contract": "c/x.yaml", "freshness_minutes": 60, "pii": False, "upstream": []},
            "mart.y": {"domain": "b", "owner": "b-team", "contract": "c/y.yaml", "freshness_minutes": 120, "pii": False, "upstream": ["raw.x"]},
        },
    }


def rules(registry):
    return sorted((f.rule, f.product) for f in dr.check(registry))


def test_clean_registry_has_no_findings(clean):
    assert dr.check(clean) == []
    dr.gate(clean)


def test_shop_registry_findings_are_pinned():
    reg = dr.load()
    assert (len(reg["products"]), len(reg["teams"])) == (16, 5)
    assert rules(reg) == [
        ("contract-missing", "ml.churn_features"), ("domain-cycle", "marketing"), ("domain-cycle", "sales"),
        ("no-on-call", "mart.delivery_delay"), ("no-on-call", "raw.shipments"),
        ("owner-missing", "raw.address_book"), ("owner-unknown", "mart.shipping_cost"),
        ("pii-no-policy", "raw.address_book"), ("slo-missing", "ml.churn_features"),
        ("upstream-dangling", "mart.pipeline_health")]
    with pytest.raises(dr.RegistryError):
        dr.gate(reg)


@pytest.mark.parametrize("mutate, expected", [
    (lambda r: r["products"]["raw.x"].update(owner=None), [("owner-missing", "raw.x")]),
    (lambda r: r["products"]["raw.x"].update(owner="c-team"), [("owner-unknown", "raw.x")]),
    (lambda r: r["products"]["raw.x"].update(contract=None), [("contract-missing", "raw.x")]),
    (lambda r: r["products"]["raw.x"].update(freshness_minutes=None), [("slo-missing", "raw.x")]),
    (lambda r: r["products"]["raw.x"].update(pii=True), [("pii-no-policy", "raw.x")]),
    (lambda r: r["teams"]["a-team"].update(on_call=False), [("no-on-call", "raw.x")]),
    (lambda r: r["products"]["mart.y"].update(upstream=["raw.x", "raw.zzz"]), [("upstream-dangling", "mart.y")]),
    (lambda r: r["products"]["raw.x"].update(ownr="a-team"), [("field-unknown", "raw.x")]),
    (lambda r: r["products"]["raw.x"].pop("pii"), [("field-missing", "raw.x")]),
    (lambda r: r["products"]["raw.x"].update(upstream=["mart.y"]), [("domain-cycle", "a"), ("domain-cycle", "b"), ("product-cycle", "mart.y"), ("product-cycle", "raw.x")]),
])
def test_each_rule_catches_its_own_hole(clean, mutate, expected):
    mutate(clean)
    assert rules(clean) == expected


def test_contract_and_slo_are_only_required_when_another_domain_uses_it(clean):
    clean["products"]["mart.y"].update(contract=None, freshness_minutes=None)  # 使う人がいない
    assert dr.check(clean) == []


def test_empty_or_missing_registry_fails_closed():
    for bad in ({}, {"teams": {}, "products": {}}, {"teams": {"a": {}}}):
        with pytest.raises(dr.RegistryError):
            dr.check(bad)


def test_scaffold_makes_four_files_that_pass_the_registry_check():
    reg = dr.load()
    spec = {"name": "mart.refund_rate", "domain": "sales", "owner": "sales-analytics", "upstream": ["raw.orders"], "pii": False}
    files = golden_path.scaffold(spec, reg)
    assert sorted(files) == [f"mart.refund_rate/{n}" for n in ("alerts.yaml", "ci.yaml", "contract.yaml", "product.yaml")]
    assert [len(t.splitlines()) for p, t in sorted(files.items())] == [4, 4, 6, 8]
    assert golden_path.check_scaffold(files, reg) == []
    pii = golden_path.scaffold({**spec, "name": "mart.refund_pii", "pii": True}, reg)
    assert "access_policy: deny-until-approved" in pii["mart.refund_pii/product.yaml"]
    assert golden_path.check_scaffold(pii, reg) == []


@pytest.mark.parametrize("change", [
    {"name": "refund_rate"}, {"name": "Mart.Refund"}, {"owner": "logistic-team"},
    {"owner": "marketing-team"},  # 領域が違うチーム
])
def test_scaffold_refuses_bad_specs(change):
    spec = {"name": "mart.refund_rate", "domain": "sales", "owner": "sales-analytics", "upstream": [], "pii": False}
    with pytest.raises(ValueError):
        golden_path.scaffold({**spec, **change}, dr.load())


def test_scaffold_refuses_missing_or_extra_fields_and_check_needs_a_manifest():
    reg = dr.load()
    with pytest.raises(ValueError):
        golden_path.scaffold({"name": "mart.a", "domain": "sales", "owner": "sales-analytics", "upstream": []}, reg)
    with pytest.raises(ValueError):
        golden_path.check_scaffold({"x/contract.yaml": "a: 1"}, reg)


def test_scaffold_with_a_dangling_upstream_is_caught_by_the_check():
    reg = dr.load()
    spec = {"name": "mart.refund_rate", "domain": "sales", "owner": "sales-analytics", "upstream": ["raw.nothing"], "pii": False}
    found = golden_path.check_scaffold(golden_path.scaffold(spec, reg), reg)
    assert [(f.rule, f.product) for f in found] == [("upstream-dangling", "mart.refund_rate")]


def test_queue_formula_and_simulation_agree_where_the_formula_exists():
    lam, mu = queue_sim.rates(4, 0)
    assert (lam, mu) == (8, 15)
    assert round(queue_sim.analytic_wait_days(lam, mu), 2) == 0.38
    mean, p90 = queue_sim.summarize(lam, mu)
    assert (round(mean, 2), round(p90, 2)) == (0.38, 1.2)
    assert mean == pytest.approx(queue_sim.analytic_wait_days(lam, mu), rel=0.05)
    mean6, p90_6 = queue_sim.summarize(*queue_sim.rates(6, 0))
    assert (round(mean6, 2), round(p90_6, 2)) == (1.3, 3.38)


def test_overloaded_window_has_no_steady_state_and_waits_blow_up():
    lam, mu = queue_sim.rates(8, 0)
    assert queue_sim.analytic_wait_days(lam, mu) is None
    mean, p90 = queue_sim.summarize(lam, mu)
    assert (round(mean, 2), round(p90, 2)) == (12.61, 22.29)
    # 同じ 8 チームでも、6 割が自分で済めば待ちはほぼ消える
    mean_ss, _ = queue_sim.summarize(*queue_sim.rates(8, 0.6))
    assert round(mean_ss, 2) == 0.25


def test_template_is_rejected_and_the_filled_review_passes():
    errors = design_review.lint_file(HERE / "design_review_template.md")
    assert len(errors) == 9 and "「背景と目的」が空です" in errors
    assert design_review.lint_file(HERE / "review_filled.md") == []


@pytest.fixture
def filled():
    return (HERE / "review_filled.md").read_text(encoding="utf-8")


def test_review_lint_catches_each_gap(filled):
    assert design_review.lint("") == ["文書が空です"]
    assert design_review.lint(filled.replace("## 移行と戻し方", "## 移行")) == ["見出し「移行と戻し方」がありません"]
    one_option = filled.replace("- 案 A: 現状維持。遅れは利用者の連絡で知る。\n", "").replace("- 案 C:", "- 他の案:")
    assert design_review.lint(one_option) == ["代替案が 2 つ未満です (現状維持を含めて 2 つ以上)"]
    assert design_review.lint(filled.replace("- 承認者: 鈴木 (platform-team)", "- 承認者:")) == ["承認者がいません"]
    no_owner = filled.replace(" (回答する人: sales-analytics、期限: 次の会議まで)", "")
    assert len(design_review.lint(no_owner)) == 1 and "回答する人" in design_review.lint(no_owner)[0]
    left = filled.replace("契約 contracts/churn_features.yaml と", "<契約> と")
    assert design_review.lint(left) == ["「提案」に雛形の <…> が残っています"]


def test_fixing_one_product_removes_exactly_its_two_findings():
    reg = dr.load()
    before = set(dr.check(reg))
    reg["products"]["ml.churn_features"].update(contract="contracts/churn_features.yaml", freshness_minutes=1440)
    after = set(dr.check(reg))
    assert before - after == {f for f in before if f.product == "ml.churn_features"}
    assert len(before) == 10 and len(after) == 8 and after < before


def test_numbers_used_in_the_exercises():
    lam, mu = queue_sim.rates(5, 0)
    assert round(queue_sim.analytic_wait_days(lam, mu), 2) == 0.67
    lam, mu = queue_sim.rates(10, 0.4)
    assert (lam / mu, round(queue_sim.analytic_wait_days(lam, mu), 2)) == (0.8, 1.33)
    reg = dr.load()
    reg["teams"]["logistics-team"]["on_call"] = True
    assert len(dr.check(reg)) == 8 and not any(f.rule == "no-on-call" for f in dr.check(reg))


def test_owner_from_another_domain_and_self_reference_are_caught(clean):
    clean["products"]["raw.x"].update(owner="b-team")
    assert rules(clean) == [("owner-domain-mismatch", "raw.x")]
    clean["products"]["raw.x"].update(owner="a-team", upstream=["raw.x"])
    assert rules(clean) == [("product-cycle", "raw.x")]


def test_longer_product_cycle_inside_one_domain(clean):
    clean["products"]["raw.z"] = {"domain": "a", "owner": "a-team", "contract": None, "freshness_minutes": None,
                                  "pii": False, "upstream": ["raw.w"]}
    clean["products"]["raw.w"] = {"domain": "a", "owner": "a-team", "contract": None, "freshness_minutes": None,
                                  "pii": False, "upstream": ["raw.z"]}
    assert rules(clean) == [("product-cycle", "raw.w"), ("product-cycle", "raw.z")]
    assert dr.product_cycles(dr.load()["products"]) == []


def test_pk_formula_matches_mm1_at_cv_one_and_simulation_follows_it():
    lam, mu = queue_sim.rates(6, 0)
    assert queue_sim.pk_wait_days(lam, mu, 1.0) == pytest.approx(queue_sim.analytic_wait_days(lam, mu))
    got = {}
    for cv in (0.5, 1.0, 2.0, 3.0):
        mean, p90 = queue_sim.summarize(lam, mu, cv=cv)
        got[cv] = (round(queue_sim.pk_wait_days(lam, mu, cv), 2), round(mean, 2), round(p90, 2))
    assert got == {0.5: (0.83, 0.81, 2.11), 1.0: (1.33, 1.3, 3.38), 2.0: (3.33, 2.97, 8.03), 3.0: (6.67, 4.94, 12.88)}
    lam, mu = queue_sim.rates(8, 0.6)
    mean, p90 = queue_sim.summarize(lam, mu, cv=2.0)
    assert (round(queue_sim.pk_wait_days(lam, mu, 2.0), 2), round(mean, 2), round(p90, 2)) == (0.62, 0.58, 1.96)
    mean3, p90_3 = queue_sim.summarize(lam, mu, cv=3.0)
    assert (round(queue_sim.pk_wait_days(lam, mu, 3.0), 2), round(mean3, 2), round(p90_3, 2)) == (1.24, 1.03, 3.58)
    assert queue_sim.pk_wait_days(*queue_sim.rates(8, 0), 2.0) is None


def test_break_even_numbers():
    assert [round(queue_sim.min_self_serve_share(n), 2) for n in (6, 8, 10)] == [0.0, 0.25, 0.4]
    assert [round(queue_sim.payback_weeks(n, s), 1) for n, s in ((8, 0.25), (8, 0.6), (10, 0.4))] == [11.3, 4.7, 5.7]
    lam, mu = queue_sim.rates(8, queue_sim.min_self_serve_share(8))
    assert lam / mu == pytest.approx(0.8)


def test_review_needs_a_conclusion_and_exact_none(filled):
    assert design_review.lint(filled.replace("- 結論: 条件付き採用", "- 結論:")) == ["結論がありません"]
    assert design_review.lint(filled.replace("- 結論: 条件付き採用\n", "")) == ["結論がありません"]
    none = filled.replace("- 利用先の mart.customer_ltv が古い値を許せる日数 (回答する人: sales-analytics、期限: 次の会議まで)", "- なし")
    assert design_review.lint(none) == []
    loose = none.replace("- なし", "- なしかもしれない")
    assert len(design_review.lint(loose)) == 1


def test_domain_mismatch_does_not_hide_the_missing_on_call(clean):
    clean["products"]["raw.x"].update(owner="b-team")
    clean["teams"]["b-team"]["on_call"] = False
    assert rules(clean) == [("no-on-call", "mart.y"), ("no-on-call", "raw.x"), ("owner-domain-mismatch", "raw.x")]


def test_tco_numbers_and_break_even():
    got = {n: [round(tco.cumulative_cost(n, m) / 10000) for m in (12, 24, 36)] for n in tco.OPTIONS}
    assert got == {"build": [345, 465, 585], "oss": [269, 464, 658], "buy": [264, 498, 732]}
    assert [tco.break_even_month(a, b) for a, b in (("oss", "buy"), ("build", "buy"), ("build", "oss"))] == [14, 21, 25]
    assert tco.cheapest(13) == "buy"
    assert [tco.cheapest(m) for m in (6, 14, 25, 36)] == ["buy", "oss", "build", "build"]


def test_tco_build_is_sensitive_to_maintenance_hours():
    limit = tco.max_build_hours()
    assert limit == 14
    assert tco.cumulative_cost("build", 36, limit) <= tco.cumulative_cost("oss", 36)
    assert tco.cumulative_cost("build", 36, limit + 1) > tco.cumulative_cost("oss", 36)


def test_tco_break_even_none_and_exercise_value(monkeypatch):
    assert tco.break_even_month("build", "oss") == 25
    monkeypatch.setattr(tco, "MONTHS", 20)
    assert tco.break_even_month("build", "oss") is None
    monkeypatch.undo()
    monkeypatch.setitem(tco.OPTIONS["buy"], "monthly_cash", 100_000)
    assert tco.cumulative_cost("buy", 36) == 5_520_000
    assert tco.cheapest(36) == "buy"


def test_ledger_freshness_matches_chapter7_contract():
    """台帳の鍵と値は、第7章の契約 (sla.freshness_minutes) と同じです。"""
    import yaml
    contract = yaml.safe_load((HERE.parent / "a07" / "contracts" / "orders.contract.yaml").read_text(encoding="utf-8"))
    ledger = yaml.safe_load((HERE / "registry.yaml").read_text(encoding="utf-8"))
    assert ledger["products"]["raw.orders"]["freshness_minutes"] == contract["sla"]["freshness_minutes"] == 60
