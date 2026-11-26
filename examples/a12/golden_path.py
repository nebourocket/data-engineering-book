"""第12章: 舗装された道 (golden path)。チームが 5 項目を書くと、台帳の項目・契約の雛形・CI・アラートを出します。"""
import re

import yaml

from domain_registry import check

NAME_RE = re.compile(r"^(raw|mart|ml|platform)\.[a-z][a-z0-9_]*$")
SPEC_FIELDS = {"name", "domain", "owner", "upstream", "pii"}
DEFAULT_SLO_MINUTES = 1440  # 指定が無ければ 1 日。SLO を決めていない表に、暗黙の約束を作らないための値
DEFAULT_ACCESS_POLICY = "deny-until-approved"


def scaffold(spec, registry):
    """spec (5 項目) からファイルの一式を {パス: 中身} で返します。台帳に無いチーム・領域は拒否します。"""
    if set(spec) != SPEC_FIELDS:
        raise ValueError(f"項目は {sorted(SPEC_FIELDS)} の 5 つです: {sorted(set(spec) ^ SPEC_FIELDS)}")
    if not NAME_RE.match(spec["name"]):
        raise ValueError(f"名前は raw./mart./ml./platform. で始まる小文字です: {spec['name']}")
    team = registry["teams"].get(spec["owner"])
    if team is None or team["domain"] != spec["domain"]:
        raise ValueError(f"チーム {spec['owner']} は領域 {spec['domain']} の持ち主として台帳にありません")
    entry = {
        "domain": spec["domain"], "owner": spec["owner"],
        "contract": f"contracts/{spec['name']}.yaml", "freshness_minutes": DEFAULT_SLO_MINUTES,
        "pii": spec["pii"], "upstream": list(spec["upstream"]),
    }
    if spec["pii"]:
        entry["access_policy"] = DEFAULT_ACCESS_POLICY
    name = spec["name"]
    return {
        f"{name}/product.yaml": yaml.safe_dump({name: entry}, allow_unicode=True, sort_keys=False),
        f"{name}/contract.yaml": yaml.safe_dump(
            {"name": name, "version": "0.1.0", "owner": spec["owner"],
             "sla": {"freshness_minutes": DEFAULT_SLO_MINUTES}, "compatibility": "backward"},
            allow_unicode=True, sort_keys=False),
        f"{name}/ci.yaml": yaml.safe_dump(
            {"steps": ["pytest", "registry-gate", "contract-compat"]}, sort_keys=False),
        f"{name}/alerts.yaml": yaml.safe_dump(
            {"alerts": [{"kind": "freshness", "minutes": DEFAULT_SLO_MINUTES, "route": spec["owner"]}]},
            allow_unicode=True, sort_keys=False),
    }


def check_scaffold(files, registry):
    """出来たファイルを台帳に足して検査し、新しく出た Finding を返します。product.yaml が無ければ失敗します。"""
    manifests = [yaml.safe_load(text) for path, text in files.items() if path.endswith("/product.yaml")]
    if len(manifests) != 1:
        raise ValueError("product.yaml がちょうど 1 つ要ります")
    merged = {"teams": registry["teams"], "products": {**registry["products"], **manifests[0]}}
    before = set(check(registry))
    return [f for f in check(merged) if f not in before]
