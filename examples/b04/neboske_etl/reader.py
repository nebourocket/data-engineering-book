"""CSV を 1 行ずつ読むジェネレータ。"""
import csv
from collections.abc import Iterator
from pathlib import Path

EXPECTED_COLUMNS = ["order_id", "customer_id", "ordered_at", "status", "item_count", "total_amount"]


def iter_rows(path: Path) -> Iterator[dict[str, str]]:
    """CSV の行を、見出しをキーにした dict として 1 行ずつ返します。"""
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in EXPECTED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: 必要な列がありません: {', '.join(missing)}")
        yield from reader
