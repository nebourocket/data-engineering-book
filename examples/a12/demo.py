"""第12章の出力をまとめて出します (外部サービスは要りません)。"""
import collections
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import design_review  # noqa: E402
import domain_registry as dr  # noqa: E402
import golden_path  # noqa: E402
import queue_sim  # noqa: E402
import tco  # noqa: E402

HERE = Path(__file__).parent


def show(title):
    print(f"--- {title}")


if __name__ == "__main__":
    reg = dr.load()

    show("registry check")
    found = dr.check(reg)
    print(f"products={len(reg['products'])} teams={len(reg['teams'])} findings={len(found)}")
    for f in found:
        print(f"{f.rule:18s} {f.product:22s} {f.message}")
    print(dict(sorted(collections.Counter(f.rule for f in found).items())))
    try:
        dr.gate(reg)
    except dr.RegistryError as e:
        print("gate ->", type(e).__name__)

    show("after the review")
    fixed = copy.deepcopy(reg)
    fixed["products"]["ml.churn_features"].update(contract="contracts/churn_features.yaml", freshness_minutes=1440)
    after = dr.check(fixed)
    print(f"findings {len(found)} -> {len(after)}")
    print(dict(sorted(collections.Counter(f.rule for f in after).items())))

    show("golden path")
    spec = {"name": "mart.refund_rate", "domain": "sales", "owner": "sales-analytics",
            "upstream": ["raw.orders"], "pii": False}
    files = golden_path.scaffold(spec, reg)
    for path, text in files.items():
        print(f"{path} ({len(text.splitlines())} lines)")
    print(files["mart.refund_rate/product.yaml"], end="")
    print("new findings:", golden_path.check_scaffold(files, reg))
    try:
        golden_path.scaffold({**spec, "owner": "logistic-team"}, reg)
    except ValueError as e:
        print("refused:", e)

    show("queue")
    for share in (0, 0.6):
        for n in (2, 4, 6, 7, 8, 10):
            lam, mu = queue_sim.rates(n, share)
            exact = queue_sim.analytic_wait_days(lam, mu)
            mean, p90 = queue_sim.summarize(lam, mu)
            print(f"self_serve={share:.1f} teams={n:2d} arrivals/wk={lam:4.1f} rho={lam / mu:.2f} "
                  f"formula={'  inf' if exact is None else f'{exact:5.2f}'} sim_mean={mean:5.2f} sim_p90={p90:5.2f} (days)")

    show("sensitivity")
    for n, share in ((6, 0), (8, 0.6)):
        lam, mu = queue_sim.rates(n, share)
        for cv in (0.5, 1.0, 2.0, 3.0):
            mean, p90 = queue_sim.summarize(lam, mu, cv=cv)
            print(f"teams={n} self_serve={share:.1f} rho={lam / mu:.2f} cv={cv:.1f} "
                  f"formula={queue_sim.pk_wait_days(lam, mu, cv):5.2f} sim_mean={mean:5.2f} sim_p90={p90:5.2f} (days)")

    show("break-even")
    for n in (6, 8, 10):
        print(f"teams={n} min self-serve share for rho<=0.8: {queue_sim.min_self_serve_share(n):.2f}")
    for n, share in ((8, 0.25), (8, 0.6), (10, 0.4)):
        print(f"teams={n} share={share:.2f} payback={queue_sim.payback_weeks(n, share):.1f} weeks "
              f"(build {queue_sim.BUILD_HOURS} h)")

    show("design review lint")
    for name in ("design_review_template.md", "review_filled.md"):
        print(name, "->", design_review.lint_file(HERE / name))
    broken = (HERE / "review_filled.md").read_text(encoding="utf-8").replace("## 失敗の仕方", "## メモ")
    print("renamed section ->", design_review.lint(broken))

    show("tco")
    for name in tco.OPTIONS:
        print(name, [f"{tco.cumulative_cost(name, m) / 10000:.0f}" for m in (12, 24, 36)], "(man-yen at 12/24/36 months)")
    for a, b in (("oss", "buy"), ("build", "buy"), ("build", "oss")):
        print(f"{a} <= {b} from month {tco.break_even_month(a, b)}")
    print("cheapest at month 6/14/25/36:", [tco.cheapest(m) for m in (6, 14, 25, 36)])
    print("build stays cheapest at 36 months up to", tco.max_build_hours(), "h/month")
