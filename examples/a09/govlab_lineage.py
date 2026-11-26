"""リネージから PII の行き先をたどる: 第8章のイベントの列から、PII を持つ表の下流を数えます。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "a08"))
from lineage_events import build_graph, downstream, one_night  # noqa: E402

# 探索 (govlab_scan) が見る表の名前 → リネージ (第8章) での表の名前
LINEAGE_NAME = {"orders": "raw.orders"}


def pii_tables(hits):
    """scan の結果 {(表, 列, 種類): 行数} から、PII が見つかった表をリネージの名前で返します。"""
    return sorted({LINEAGE_NAME[table] for table, _, _ in hits if table in LINEAGE_NAME})


def pii_trail(events, tables):
    """PII を持つ表ごとに、そこから流れ込む下流の表を、近い順に返します。"""
    graph = build_graph(events)
    return {t: downstream(graph, t) for t in tables}


def unreviewed(trail, reviewed):
    """PII の行き先のうち、権限の棚卸しがまだ済んでいない表を返します。"""
    return sorted({d for ds in trail.values() for d in ds} - set(reviewed))

