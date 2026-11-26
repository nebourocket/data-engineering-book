"""集計表 (aggregate) と、パーティション・クラスタリングで読む量を減らす。"""
import tempfile
from pathlib import Path

import pyarrow.parquet as pq

AGG_SQL = """
CREATE TABLE agg_sales_month AS
SELECT month, prefecture, category, sum(amount) AS revenue, count(*) AS lines
FROM obt_sales WHERE status <> 'cancelled' GROUP BY ALL
"""
QUERY_AGG = "SELECT month, prefecture, category, sum(revenue) FROM agg_sales_month GROUP BY ALL ORDER BY ALL"


def column_bytes(path, columns):
    meta = pq.ParquetFile(path).metadata
    total = 0
    for g in range(meta.num_row_groups):
        for c in range(meta.num_columns):
            col = meta.row_group(g).column(c)
            if col.path_in_schema in columns:
                total += col.total_compressed_size
    return total


def aggregate_scan(con):
    """同じ問いを OBT と集計表で答えたときの、行数と読む列のバイト数 (Parquet) を比べます。"""
    with tempfile.TemporaryDirectory() as tmp:
        for t in ("obt_sales", "agg_sales_month"):
            con.execute(f"COPY {t} TO '{tmp}/{t}.parquet' (FORMAT parquet)")
        obt = column_bytes(f"{tmp}/obt_sales.parquet", {"month", "prefecture", "category", "status", "amount"})
        agg = column_bytes(f"{tmp}/agg_sales_month.parquet", {"month", "prefecture", "category", "revenue"})
    rows = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("obt_sales", "agg_sales_month")}
    same = (con.execute("SELECT month, prefecture, category, sum(amount) FROM obt_sales "
                        "WHERE status <> 'cancelled' GROUP BY ALL ORDER BY ALL").fetchall()
            == con.execute(QUERY_AGG).fetchall())
    return {"rows": rows, "scanned_bytes": {"obt": obt, "aggregate": agg}, "same_answer": same}


def partition_and_cluster(con, row_group_size=50000):
    """月でパーティションに分けると 1 か月の問いが読むファイルは何本か。都道府県で並べると読み飛ばせる行グループは何個か。"""
    with tempfile.TemporaryDirectory() as tmp:
        part = Path(tmp) / "by_month"
        con.execute(f"COPY obt_sales TO '{part}' (FORMAT parquet, PARTITION_BY (month))")
        files = sorted(part.glob("month=*/*.parquet"))
        wanted = [f for f in files if f.parent.name == "month=2026-03"]
        flat = {}
        for name, order in [("unsorted", "order_id, line_no"), ("clustered", "prefecture, order_id, line_no")]:
            path = f"{tmp}/{name}.parquet"
            con.execute(f"COPY (SELECT * FROM obt_sales ORDER BY {order}) TO '{path}' "
                        f"(FORMAT parquet, ROW_GROUP_SIZE {row_group_size})")
            meta = pq.ParquetFile(path).metadata
            idx = [meta.schema.names.index("prefecture")] if "prefecture" in meta.schema.names else None
            col = [i for i in range(meta.num_columns) if meta.row_group(0).column(i).path_in_schema == "prefecture"][0]
            hit = 0
            for g in range(meta.num_row_groups):
                st = meta.row_group(g).column(col).statistics
                if st.min <= "東京" <= st.max:
                    hit += 1
            flat[name] = {"row_groups": meta.num_row_groups, "row_groups_that_may_contain_tokyo": hit}
    return {"partition_files": len(files), "files_read_for_one_month": len(wanted), **flat}
