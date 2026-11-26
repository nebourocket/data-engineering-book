"""Debezium の PostgreSQL コネクタ設定 (JSON) の形を検査します。Kafka Connect には接続しません。"""
import json
import re
from pathlib import Path

REQUIRED = ["connector.class", "database.hostname", "database.user", "database.password",
            "database.dbname", "plugin.name", "slot.name", "publication.name", "topic.prefix",
            "table.include.list"]


def check_connector(doc):
    """設定の問題を文字列のリストで返します。空なら形は問題ありません。"""
    cfg = doc.get("config", {})
    problems = [f"必須の設定がありません: {key}" for key in REQUIRED if key not in cfg]
    if cfg.get("plugin.name") not in (None, "pgoutput"):
        problems.append("plugin.name は pgoutput にします (PostgreSQL 10 以降は追加の拡張が要りません)")
    if "slot.name" in cfg and not re.fullmatch(r"[a-z0-9_]{1,63}", cfg["slot.name"]):
        problems.append("slot.name は小文字・数字・_ だけで 63 文字以内です (PostgreSQL の規則)")
    password = cfg.get("database.password", "")
    if password and not password.startswith("${"):
        problems.append("database.password を設定に直接書かず、シークレットの参照 ${...} にします")
    for table in filter(None, cfg.get("table.include.list", "").split(",")):
        if "." not in table:
            problems.append(f"table.include.list は schema.table の形にします: {table}")
    if int(cfg.get("heartbeat.interval.ms", "0")) <= 0:
        problems.append("heartbeat.interval.ms が 0 以下です (更新の少ない表だけを読むと WAL が減りません)")
    return problems


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
