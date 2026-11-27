"""第8章: OpenLineage の RunEvent を組み立て、イベントの列から依存の向きを復元して影響範囲を数えます。

仕様の項目名は OpenLineage 2-0-2 の JSON Schema に合わせています。この章のコードは、公式の検証器や
OpenLineage のクライアントライブラリは使わず、辞書を自分で組み立てます。
"""
import json
import uuid
from collections import deque

PRODUCER = "https://example.com/neboske/pipeline"
RUN_EVENT_URL = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent"
SCHEMA_FACET_URL = "https://openlineage.io/spec/facets/1-1-1/SchemaDatasetFacet.json#/$defs/SchemaDatasetFacet"
NAMESPACE = "neboske"

# ジョブの名前 → (入力の表, 出力の表)。表は名前だけ。列は ORDERS_FIELDS のように別に持つ。
JOBS = {
    "ingest_orders": (["app.orders"], ["raw.orders"]),
    "ingest_events": (["app.events"], ["raw.events"]),
    "ingest_order_items": (["app.order_items"], ["raw.order_items"]),
    "build_fact_sales": (["raw.orders", "raw.order_items"], ["mart.fact_sales"]),
    "daily_revenue": (["mart.fact_sales"], ["mart.daily_revenue"]),
    "churn_features": (["raw.orders", "raw.events"], ["ml.churn_features"]),
}
ORDERS_FIELDS = [("order_id", "INTEGER"), ("customer_id", "INTEGER"), ("status", "VARCHAR"),
                 ("ordered_at", "VARCHAR"), ("total_amount", "INTEGER")]


def dataset(name, fields=None):
    """OpenLineage のデータセット (namespace と name)。fields があれば schema ファセットを付ける。"""
    ds = {"namespace": NAMESPACE, "name": name}
    if fields:
        ds["facets"] = {"schema": {
            "_producer": PRODUCER, "_schemaURL": SCHEMA_FACET_URL,
            "fields": [{"name": n, "type": t} for n, t in fields]}}
    return ds


def run_event(event_type, event_time, run_id, job, inputs, outputs):
    """RunEvent を 1 件、辞書で返す。eventType は START / COMPLETE / FAIL など。"""
    return {"eventType": event_type, "eventTime": event_time, "run": {"runId": run_id},
            "job": {"namespace": NAMESPACE, "name": job},
            "inputs": inputs, "outputs": outputs, "producer": PRODUCER, "schemaURL": RUN_EVENT_URL}


def emit_run(job, start, end, orders_fields=ORDERS_FIELDS, failed=False):
    """1 回の実行で出るイベント (START と COMPLETE か FAIL) を返す。run_id は job と start から決める。"""
    ins, outs = JOBS[job]
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{job}/{start}"))
    out_ds = [dataset(n, orders_fields if n == "raw.orders" else None) for n in outs]
    return [run_event("START", start, run_id, job, [dataset(n) for n in ins], []),
            run_event("FAIL" if failed else "COMPLETE", end, run_id, job, [dataset(n) for n in ins], out_ds)]


def one_night(day="2026-04-01", orders_fields=ORDERS_FIELDS, failed_jobs=()):
    """1 晩ぶん、全ジョブを順に動かしたイベントの列 (JSON 風の辞書のリスト)。"""
    events = []
    for i, job in enumerate(JOBS):
        start, end = f"{day}T0{i}:00:00Z", f"{day}T0{i}:20:00Z"
        events += emit_run(job, start, end, orders_fields, failed=job in failed_jobs)
    return events


def build_graph(events):
    """全イベント (START・COMPLETE・FAIL) から、「入力の表 → 出力の表」の構造を集める。失敗した実行も、依存の構造としては数える。"""
    graph = {}
    for e in events:
        for i in e["inputs"]:
            for o in e["outputs"]:
                graph.setdefault(i["name"], set()).add(o["name"])
    return graph


def downstream(graph, name):
    """name の変更・故障の影響を受ける表を、近い順に返す (幅優先)。"""
    seen, order, queue = {name}, [], deque([name])
    while queue:
        for nxt in sorted(graph.get(queue.popleft(), ())):
            if nxt not in seen:
                seen.add(nxt)
                order.append(nxt)
                queue.append(nxt)
    return order


def stale_tables(events):
    """失敗 (FAIL) した実行の出力は古いままです。(古いままの表, その下流で古い入力を読む表) を返します。"""
    graph = build_graph(events)
    stale = sorted({o["name"] for e in events if e["eventType"] == "FAIL" for o in e["outputs"]})
    behind = sorted({d for name in stale for d in downstream(graph, name)} - set(stale))
    return stale, behind


def schema_drift(events, name, contract_schema):
    """イベントの schema ファセットと契約 (第7章の JSON Schema) の列を比べ、(契約に無い列, 契約の必須なのにイベントに無い列) を返す。"""
    for e in events:
        for o in e["outputs"]:
            if o["name"] == name and "facets" in o:
                actual = {f["name"] for f in o["facets"]["schema"]["fields"]}
                return (sorted(actual - set(contract_schema["properties"])),
                        sorted(set(contract_schema["required"]) - actual))
    raise KeyError(name)


def to_json_lines(events):
    return "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in events)
