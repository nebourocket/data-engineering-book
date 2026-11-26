"""第16章の、コードから作る表 (data/tables/ の CSV)。

書き直すとき: python examples/b16/serving_tables.py
"""
import csv
import sqlite3
import tempfile
from pathlib import Path

import duckdb
from reverse_etl import sync_contacts
from sales_metrics import SALES_DEFINITIONS, monthly_by_definition
from shop_warehouse import AS_OF, build_warehouse, refresh_summary

TABLES = Path(__file__).resolve().parents[2] / "data" / "tables"
LATER = "2026-07-15"


def sales_definition_rows() -> list[list]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "w.duckdb"
        build_warehouse(path)
        con = duckdb.connect(str(path), read_only=True)
        try:
            return [list(row) for row in monthly_by_definition(con)]
        finally:
            con.close()


def sync_run_rows() -> list[list]:
    """同じ同期を 3 回動かした記録。1 回目は新規、2 回目は同じ日の再実行、3 回目は基準日を進めた日。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "w.duckdb"
        build_warehouse(path)
        warehouse = duckdb.connect(str(path))
        crm = sqlite3.connect(":memory:")
        rows = []
        try:
            for label, as_of in [("1 回目", AS_OF), ("2 回目 (同じ日)", AS_OF), ("3 回目 (基準日を進めた)", LATER)]:
                refresh_summary(warehouse, as_of)
                r = sync_contacts(warehouse, crm, as_of)
                rows.append([label, as_of, r["read"], r["inserted"], r["updated"], r["unchanged"]])
        finally:
            warehouse.close()
            crm.close()
        return rows


def tables() -> dict[str, tuple[list[str], list[list]]]:
    return {
        "b16-sales-definitions": (["月", *SALES_DEFINITIONS], sales_definition_rows()),
        "b16-sync-runs": (["実行", "基準日", "読んだ行", "新規", "更新", "変化なし"], sync_run_rows()),
    }


if __name__ == "__main__":
    for name, (header, rows) in tables().items():
        with (TABLES / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        print(f"{name}.csv を書きました（{len(rows)} 行）")
