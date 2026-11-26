"""第7章のケーススタディ: 受注アプリが列名を変えた日、契約が無い場合と有る場合で何が起きるか。"""
import copy
import json
import time

import duckdb

from contract_check import ci_gate, validate_batch
from schema_evolution import evolution_gate

RELEASE_DAY = "2026-04-01"  # この日以降の注文は、新しい受注アプリが出す


def rename_release(orders, release_day=RELEASE_DAY):
    """受注アプリの「整理」: release_day 以降の注文は total_amount ではなく amount で出る。"""
    return [{**{k: v for k, v in o.items() if k != "total_amount"}, "amount": o["total_amount"]}
            if o["ordered_at"] >= release_day else o for o in orders]


def renamed_schema(old):
    """上の変更を表すスキーマ (CI の関門に渡す)。"""
    new = copy.deepcopy(old)
    new["properties"]["amount"] = new["properties"].pop("total_amount")
    new["required"] = ["amount" if n == "total_amount" else n for n in new["required"]]
    return new


def expanded_schema(old):
    """並走の 1 歩目: total_amount を残したまま、任意の列 amount を足す。"""
    new = copy.deepcopy(old)
    new["properties"]["amount"] = copy.deepcopy(new["properties"]["total_amount"])
    return new


def contracted_schema(expanded):
    """並走の最後の歩: total_amount をやめ、amount を必須にする。"""
    new = copy.deepcopy(expanded)
    del new["properties"]["total_amount"]
    new["required"] = ["amount" if n == "total_amount" else n for n in new["required"]]
    return new


def monthly_revenue_from_docs(docs):
    """JSON の文書を 1 列 (doc) で取り込み、月別の売上を取り出す。列が無ければ NULL になるだけで、エラーにならない。"""
    con = duckdb.connect()
    con.execute("CREATE TABLE raw_orders (doc JSON)")
    con.executemany("INSERT INTO raw_orders VALUES (?)", [(json.dumps(d),) for d in docs])
    return con.execute("""
        SELECT substr(doc->>'$.ordered_at', 1, 7) AS month,
               count(*) AS orders,
               count((doc->>'$.total_amount')::BIGINT) AS with_amount,
               sum((doc->>'$.total_amount')::BIGINT) AS revenue
        FROM raw_orders GROUP BY month ORDER BY month""").fetchall()


def ingest_with_contract(schema, docs):
    """取り込み口で契約に当て、合格を取り込み・違反を隔離表 (quarantine) に分ける。"""
    bad = {v["index"]: v["message"] for v in validate_batch(schema, docs)}
    accepted = [d for i, d in enumerate(docs) if i not in bad]
    quarantine = [(docs[i]["order_id"], msg) for i, msg in sorted(bad.items())]
    return accepted, quarantine


def validation_rate(schema, orders, repeat):
    """orders を repeat 回ぶん並べたレコードの束を検査して、1 秒あたりの件数を返す (環境で揺れる)。"""
    docs = orders * repeat
    start = time.perf_counter()
    validate_batch(schema, docs)
    return len(docs), len(docs) / (time.perf_counter() - start)



def inject_defects(orders):
    """JSON Schema を通る(型は正しい)が、中身が壊れた注文を作る: 二重送信 30 件・合計の食い違い 12 件・存在しない顧客 5 件。"""
    broken = [dict(o) for o in orders]
    for o in broken[100:112]:
        o["total_amount"] -= 100  # 値引きが合計にだけ反映された
    for o in broken[200:205]:
        o["customer_id"] = 9999
    return broken + [dict(o) for o in orders[:30]]  # 再送で同じ注文が 2 回届いた


def repair(doc):
    """直し方が分かっている違反だけ直す: 改名された amount を total_amount に戻し、status を小文字にする。"""
    fixed = dict(doc)
    if "amount" in fixed and "total_amount" not in fixed:
        fixed["total_amount"] = fixed.pop("amount")
    if isinstance(fixed.get("status"), str):
        fixed["status"] = fixed["status"].lower()
    return fixed


def replay(schema, accepted, rejected):
    """隔離した記録を直して契約に当て直し、通ったものを取り込み済みに足す。order_id をキーにするので、再投入を繰り返しても二重にならない。"""
    repaired = [repair(d) for d in rejected]
    bad = {v["index"] for v in validate_batch(schema, repaired)}
    fixed = [d for i, d in enumerate(repaired) if i not in bad]
    still_bad = [d for i, d in enumerate(repaired) if i in bad]
    merged = {d["order_id"]: d for d in accepted + fixed}
    return list(merged.values()), still_bad


def rejected_docs(schema, docs):
    """契約に通らなかった記録そのもの (ingest_with_contract は理由だけを残すので、再投入用に記録を取り出す)。"""
    bad = {v["index"] for v in validate_batch(schema, docs)}
    return [d for i, d in enumerate(docs) if i in bad]


def staged_gate(schema, records, stage):
    """導入の段階: warn は違反を表示するだけで通し、block は違反があれば止める。"""
    code = ci_gate(schema, records)
    return 0 if stage == "warn" else code
