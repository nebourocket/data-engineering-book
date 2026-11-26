"""デコードした変更を、Debezium のイベント (エンベロープ) に似た形に包みます。"""
import json

OPS = {"insert": "c", "update": "u", "delete": "d"}


def to_envelope(change, *, db):
    """行の変更 1 件を、before / after / source / op / ts_ms を持つ辞書にします。"""
    schema, table = change["table"].split(".")
    return {
        "before": change["old"],
        "after": change["new"],
        "source": {"connector": "postgresql", "db": db, "schema": schema, "table": table,
                   "txId": change["xid"], "lsn": change["lsn"]},
        "op": OPS[change["op"]],
        "ts_ms": change["ts_ms"],
    }


def event_key(change, key_column="order_id"):
    """Kafka のキー。削除のときは old から取ります。同じ行の変更が同じパーティションに行くための値です。"""
    row = change["new"] or change["old"]
    return json.dumps({key_column: row[key_column]})
