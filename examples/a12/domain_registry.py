"""第12章: データプロダクト台帳の検査。持ち主・契約・SLO・個人情報の扱い・領域をまたぐ循環を機械で確かめます。"""
from dataclasses import dataclass
from pathlib import Path

import yaml

FIELDS = {"domain", "owner", "contract", "freshness_minutes", "pii", "upstream", "access_policy"}
REQUIRED = {"domain", "owner", "contract", "freshness_minutes", "pii", "upstream"}


class RegistryError(Exception):
    """台帳に直すべき点があるときの例外。"""


@dataclass(frozen=True)
class Finding:
    rule: str
    product: str
    message: str


def load(path=None):
    path = Path(path) if path else Path(__file__).parent / "registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def consumers(products):
    """各プロダクトを upstream に挙げているプロダクトの一覧 (逆引き)。"""
    out = {name: [] for name in products}
    for name, p in products.items():
        for up in p.get("upstream") or []:
            if up in out:
                out[up].append(name)
    return out


def domain_cycles(products):
    """領域の間の依存 (上流の領域 -> 下流の領域) で、循環に入っている領域の集合を返します。"""
    edges = {}
    for p in products.values():
        for up in p.get("upstream") or []:
            if up in products and products[up].get("domain") != p.get("domain"):
                edges.setdefault(products[up].get("domain"), set()).add(p.get("domain"))

    def reach(start):
        seen, stack = set(), list(edges.get(start, ()))
        while stack:
            d = stack.pop()
            if d not in seen:
                seen.add(d)
                stack.extend(edges.get(d, ()))
        return seen

    return sorted(d for d in edges if d in reach(d))


def product_cycles(products):
    """上流をたどって自分に戻ってくるプロダクト (自分自身を上流に挙げるものを含む) の一覧。"""
    def reach(start):
        seen, stack = set(), list(products[start].get("upstream") or [])
        while stack:
            name = stack.pop()
            if name in products and name not in seen:
                seen.add(name)
                stack.extend(products[name].get("upstream") or [])
        return seen

    return sorted(name for name in products if name in reach(name))


def check(registry):
    """台帳を検査して Finding の一覧を返します。台帳が空なら失敗します (空は「問題なし」ではない)。"""
    products, teams = registry.get("products") or {}, registry.get("teams") or {}
    if not products or not teams:
        raise RegistryError("products と teams が空です。読み込みの失敗を「問題なし」と見なしません")
    found = []
    users = consumers(products)
    for name, p in sorted(products.items()):
        for missing in sorted(REQUIRED - p.keys()):
            found.append(Finding("field-missing", name, f"項目 {missing} がありません"))
        for extra in sorted(p.keys() - FIELDS):
            found.append(Finding("field-unknown", name, f"知らない項目 {extra} があります (綴りの間違い?)"))
        owner = p.get("owner")
        if not owner:
            found.append(Finding("owner-missing", name, "持ち主がいません"))
        elif owner not in teams:
            found.append(Finding("owner-unknown", name, f"持ち主 {owner} が teams にありません"))
        else:
            if teams[owner].get("domain") != p.get("domain"):
                found.append(Finding("owner-domain-mismatch", name, f"持ち主 {owner} は領域 {teams[owner].get('domain')} のチームで、プロダクトの領域 {p.get('domain')} と違います"))
            if p.get("freshness_minutes") and not teams[owner].get("on_call"):
                found.append(Finding("no-on-call", name, f"SLO があるのに {owner} に当番がありません"))
        outside = [c for c in users[name] if products[c].get("domain") != p.get("domain")]
        if outside and not p.get("contract"):
            found.append(Finding("contract-missing", name, f"他の領域 ({', '.join(outside)}) が使うのに契約がありません"))
        if outside and not p.get("freshness_minutes"):
            found.append(Finding("slo-missing", name, "他の領域が使うのに SLO がありません"))
        if p.get("pii") and not p.get("access_policy"):
            found.append(Finding("pii-no-policy", name, "個人情報なのにアクセス方針がありません"))
        for up in p.get("upstream") or []:
            if up not in products:
                found.append(Finding("upstream-dangling", name, f"上流 {up} が台帳にありません"))
    for name in product_cycles(products):
        found.append(Finding("product-cycle", name, "上流をたどると自分に戻ります"))
    for d in domain_cycles(products):
        found.append(Finding("domain-cycle", d, "領域が循環した依存に入っています"))
    return found


def gate(registry):
    """CI で使う入口。Finding が 1 つでもあれば RegistryError にします。"""
    found = check(registry)
    if found:
        raise RegistryError(f"{len(found)} 件: " + "; ".join(f"{f.rule}:{f.product}" for f in found))
