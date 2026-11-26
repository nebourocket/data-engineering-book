"""第7章: スキーマの変更が後方互換・前方互換かを、規則と実データの両方で確かめます。

扱うのは JSON Schema のうち、type・enum・minimum・maximum・required・properties・
additionalProperties (真偽値) だけです。それ以外のキーワードは、この検査では見ません。
"""
import copy

from jsonschema import Draft202012Validator

from contract_check import load_schema, shop_orders

NUMBER_TYPES = {"integer", "number"}
CHECKED = {"type", "enum", "minimum", "maximum"}  # 列の条件のうち、この検査が比べるもの
ANNOTATIONS = {"title", "description", "$comment", "default", "examples"}  # 検証に効かない注釈
TOP_LEVEL = {"$schema", "$id", "type", "properties", "required", "additionalProperties"} | ANNOTATIONS


def _types(prop):
    """type を集合にします。type が無ければ None (何でもよい)。integer は number の一部です。"""
    t = prop.get("type")
    if t is None:
        return None
    found = {t} if isinstance(t, str) else set(t)
    return found | {"integer"} if "number" in found else found


def prop_within(a, b):
    """条件 a を満たす値が、すべて条件 b も満たすなら True。"""
    ta, tb = _types(a), _types(b)
    if tb is not None and (ta is None or not ta <= tb):
        return False
    if "enum" in b and ("enum" not in a or not set(a["enum"]) <= set(b["enum"])):
        return False
    if "minimum" in b and ("minimum" not in a or a["minimum"] < b["minimum"]):
        return False
    if "maximum" in b and ("maximum" not in a or a["maximum"] > b["maximum"]):
        return False
    return True


def schema_within(a, b):
    """a で正しい記録が、すべて b でも正しいか。b に拒否される場合の理由の一覧を返します (空なら成り立つ)。"""
    reasons = []
    a_open, b_open = a.get("additionalProperties", True), b.get("additionalProperties", True)
    if a_open and not b_open:
        reasons.append("知らない列を含む記録が拒否される")
    for name in b.get("required", []):
        if name not in a.get("required", []):
            reasons.append(f"{name} を持たない記録が拒否される")
    pa, pb = a.get("properties", {}), b.get("properties", {})
    for name in sorted(pa.keys() | pb.keys()):
        sa, sb = pa.get(name), pb.get(name)
        if sa is None:
            if not a_open:
                continue  # a には列 name が現れない
            sa = {}
        if sb is None:
            if not b_open:
                reasons.append(f"{name} を含む記録が拒否される (閉じた形に無い列)")
            continue
        if not prop_within(sa, sb):
            reasons.append(f"{name} の値が拒否されることがある")
    return reasons


def unchecked(old, new):
    """この検査が比べられないキーワード (maxLength・pattern・multipleOf など) の変更を、一覧で返します。"""
    found = []
    if old.get("type") != new.get("type"):
        found.append("未対応のキーワード type (スキーマ全体) が変わった")
    ap_old, ap_new = old.get("additionalProperties", True), new.get("additionalProperties", True)
    if ap_old != ap_new and not (isinstance(ap_old, bool) and isinstance(ap_new, bool)):
        found.append("未対応のキーワード additionalProperties (真偽値でない指定) が変わった")
    for key in sorted((old.keys() | new.keys()) - TOP_LEVEL):
        if old.get(key) != new.get(key):
            found.append(f"未対応のキーワード {key} が変わった")
    po, pn = old.get("properties", {}), new.get("properties", {})
    for name in sorted(po.keys() | pn.keys()):
        a, b = po.get(name, {}), pn.get(name, {})
        for key in sorted((a.keys() | b.keys()) - CHECKED - ANNOTATIONS):
            if a.get(key) != b.get(key):
                found.append(f"{name} の未対応のキーワード {key} が変わった")
    return found


def check(old, new):
    """後方互換 (新しい読み手が古いデータを読める) と前方互換 (古い読み手が新しいデータを読める) を返します。

    unchecked が空でないときは、この検査では判定できない変更があります (passes は合格にしません)。
    """
    return {"backward": schema_within(old, new), "forward": schema_within(new, old), "unchecked": unchecked(old, new)}


def passes(result, mode):
    """mode は backward / forward / full。理由の一覧が空なら合格です。"""
    needed = ["backward", "forward"] if mode == "full" else [mode]
    return all(not result[m] for m in needed) and not result["unchecked"]


def required_bump(old, new, mode):
    """変更に必要な版の上げ方を返す。判定できない変更は "review" (人が決める)、mode を破るなら "major"、列や必須が変わるなら "minor"、それ以外は "patch"。"""
    result = check(old, new)
    if result["unchecked"]:
        return "review"
    if not passes(result, mode):
        return "major"
    changed = old.get("properties") != new.get("properties") or old.get("required") != new.get("required")
    return "minor" if changed else "patch"


def evolution_gate(old, new, mode):
    """CI の関門: 変更が mode を満たさなければ 1、満たせば 0 を返します。"""
    result = check(old, new)
    for m in (["backward", "forward"] if mode == "full" else [mode]):
        for reason in result[m]:
            print(f"  [{m}] {reason}")
    for reason in result["unchecked"]:
        print(f"  [unchecked] {reason}: 人が確認する")
    ok = passes(result, mode)
    print(f"{'PASS' if ok else 'FAIL'}: mode={mode}")
    return 0 if ok else 1


def _scenarios():
    """(名前, 古いスキーマ → 新しいスキーマにする関数, 古いレコード → 新しい生産者が出すレコードにする関数)。"""
    def add_optional(s):
        s["properties"]["coupon_code"] = {"type": "string"}

    def add_required(s):
        s["properties"]["channel"] = {"enum": ["web", "app"]}
        s["required"].append("channel")

    def drop_optional(s):
        del s["properties"]["gift_message"]

    def widen_enum(s):
        s["properties"]["status"]["enum"].append("refunded")

    def narrow_enum(s):
        s["properties"]["status"]["enum"].remove("cancelled")

    def widen_type(s):
        s["properties"]["total_amount"]["type"] = "number"

    def rename(s):
        s["properties"]["amount"] = s["properties"].pop("total_amount")
        s["required"] = ["amount" if n == "total_amount" else n for n in s["required"]]

    def relax_required(s):
        s["required"].remove("customer_id")

    def tighten_optional(s):
        s["required"].append("gift_message")

    def rename_doc(d):
        d["amount"] = d.pop("total_amount")

    return [
        ("任意の列 coupon_code を足す", add_optional, lambda d: {**d, "coupon_code": "SPRING"}),
        ("必須の列 channel を足す", add_required, lambda d: {**d, "channel": "web"}),
        ("任意の列 gift_message を削る", drop_optional, lambda d: {k: v for k, v in d.items() if k != "gift_message"}),
        ("status に refunded を足す", widen_enum, lambda d: {**d, "status": "refunded"} if d["order_id"] % 7 == 0 else d),
        ("status から cancelled を消す", narrow_enum, lambda d: d if d["status"] != "cancelled" else None),
        ("total_amount を number に広げる", widen_type, lambda d: {**d, "total_amount": d["total_amount"] + 0.5}),
        ("total_amount を amount に改名", rename, lambda d: (rename_doc(d), d)[1]),
        ("customer_id を必須から任意に", relax_required, lambda d: {k: v for k, v in d.items() if k != "customer_id"} if d["order_id"] % 5 == 0 else d),
        ("gift_message を任意から必須に", tighten_optional, lambda d: {**d, "gift_message": d.get("gift_message", "")}),
    ]


def sample_records():
    """実データ (ねぼすけ商店の注文) から、v1 で正しい記録を取り出します。gift_message は 10 件に 1 件付けます。"""
    schema = load_schema("orders.v1.json")
    validator = Draft202012Validator(schema)
    docs = [r for r in shop_orders() if validator.is_valid(r)]
    return [{**r, "gift_message": "ありがとう"} if r["order_id"] % 10 == 0 else r for r in docs]


def run_scenarios(old, open_model=False):
    """各変更を規則で判定し、実データでも古い側・新しい側のレコードを相手のスキーマに通して確かめます。

    戻り値の各行: 名前, 規則の判定 (backward, forward), 実データの判定 (backward, forward)。
    """
    docs = sample_records()
    if open_model:
        old = copy.deepcopy(old)
        old["additionalProperties"] = True
    rows = []
    for name, mutate_schema, mutate_doc in _scenarios():
        new = copy.deepcopy(old)
        mutate_schema(new)
        result = check(old, new)
        new_docs = [d for d in (mutate_doc(copy.deepcopy(d)) for d in docs) if d is not None]
        old_v, new_v = Draft202012Validator(old), Draft202012Validator(new)
        empirical = {"backward": all(new_v.is_valid(d) for d in docs),
                     "forward": all(old_v.is_valid(d) for d in new_docs)}
        rows.append((name, {m: not result[m] for m in ("backward", "forward")}, empirical))
    return rows
