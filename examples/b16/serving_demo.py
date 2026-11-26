"""第16章: 本文の出力例を作るデモ。リポジトリの直下で python examples/b16/serving_demo.py"""
import sqlite3
import tempfile
from pathlib import Path

import duckdb
from file_exchange import export_csv, publish_view, read_export
from reverse_etl import NAIVE_DDL, NAIVE_INSERT_SQL, REPLACE_SQL, apply_upsert, read_source, sync_contacts
from sales_metrics import metric_sql
from shop_warehouse import AS_OF, build_warehouse, refresh_summary


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        build_warehouse(work / "warehouse.duckdb")
        warehouse = duckdb.connect(str(work / "warehouse.duckdb"))

        print("== 指標層: 月別の売上 (定義は 1 か所) ==")
        print(warehouse.execute(metric_sql("sales", "month")).fetchall()[2])

        print("== ファイル渡し ==")
        rows = export_csv(warehouse, work / "customers.csv")
        print(rows, "行を書きました")
        print((work / "customers.csv").read_bytes()[:12])
        print(read_export(work / "customers.csv")[0])

        print("== 逆 ETL ==")
        crm = sqlite3.connect(work / "crm.sqlite")
        print("1 回目:", sync_contacts(warehouse, crm, AS_OF))
        print("2 回目:", sync_contacts(warehouse, crm, AS_OF))

        print("== 悪い書き方 ==")
        source_rows, _ = read_source(warehouse)
        crm.execute(NAIVE_DDL)
        for _ in range(2):
            crm.executemany(NAIVE_INSERT_SQL, [(*r, AS_OF) for r in source_rows])
        print("追記だけ 2 回:", crm.execute("select count(*) from contacts_naive").fetchone()[0], "行")
        crm.execute("update contacts set owner = '佐藤' where customer_id = 1")
        crm.commit()
        crm.executemany(REPLACE_SQL, [(*r, AS_OF) for r in source_rows])
        crm.commit()
        print("REPLACE のあとの owner:", crm.execute("select owner from contacts where customer_id = 1").fetchone()[0])

        print("== 読み取り専用 ==")
        warehouse.close()
        publish_view(work / "warehouse.duckdb")
        reader = duckdb.connect(str(work / "warehouse.duckdb"), read_only=True)
        print(reader.execute("select count(*) from serving_customers").fetchone()[0], "行読めます")
        try:
            reader.execute("delete from customer_summary")
        except duckdb.Error as e:
            print(str(e).split(" which")[0])
        crm.close()
        reader.close()


if __name__ == "__main__":
    main()
