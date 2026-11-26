"""第7章: JSON Schema で書いたデータ契約を、レコードの束に当てて合否を返します (CI の関門)。"""
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from neboske_shop import generate

CONTRACT_DIR = Path(__file__).parent / "contracts"
CONTRACT_KEYS = {"name", "version", "owner", "schema", "semantics", "sla", "compatibility"}
COMPAT_MODES = {"backward", "forward", "full"}


def load_schema(name):
    """契約のスキーマを読み、スキーマ自身が正しい JSON Schema かを確かめてから返します。"""
    schema = json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def load_contract(name="orders.contract.yaml"):
    """契約の書類 (YAML) を読み、必須の項目とスキーマの参照先を確かめます。"""
    contract = yaml.safe_load((CONTRACT_DIR / name).read_text(encoding="utf-8"))
    missing = CONTRACT_KEYS - contract.keys()
    assert not missing, f"契約に項目が足りません: {sorted(missing)}"
    assert contract["compatibility"] in COMPAT_MODES
    load_schema(contract["schema"])
    return contract


def shop_orders():
    """ねぼすけ商店の注文を、契約 v1 の形 (1 注文 1 レコード) に直して返します。"""
    shop = generate()
    totals = {}
    for line in shop["order_items"]:
        totals[line["order_id"]] = totals.get(line["order_id"], 0) + line["quantity"] * line["unit_price"]
    return [{"order_id": o["order_id"], "customer_id": o["customer_id"], "status": o["status"],
             "ordered_at": o["ordered_at"], "total_amount": totals[o["order_id"]]}
            for o in shop["orders"]]


def validate_batch(schema, records):
    """違反を [{index, path, message}] で返します。空なら合格です。"""
    validator = Draft202012Validator(schema)
    found = []
    for index, record in enumerate(records):
        for err in sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path)):
            found.append({"index": index, "path": "/".join(map(str, err.absolute_path)) or "(root)",
                          "message": err.message})
    return found


def ci_gate(schema, records, max_bad_rate=0.0):
    """違反したレコードの割合が上限を超えたら 1 (失敗)、超えなければ 0 (合格) を返します。"""
    if not records:
        raise ValueError("検査するレコードが 0 件です。空の束を合格にしないため、失敗として止めます")
    violations = validate_batch(schema, records)
    bad_records = len({v["index"] for v in violations})
    rate = bad_records / len(records)
    verdict = "PASS" if rate <= max_bad_rate else "FAIL"
    print(f"{verdict}: {bad_records}/{len(records)} records violate the contract (rate {rate:.4f}, limit {max_bad_rate})")
    return 0 if verdict == "PASS" else 1
