"""ケーススタディ: ねぼすけ商店が 1 倍・10 倍・100 倍になったときの、3 つのモデルの費用を測ります。"""
import statistics
import tempfile
import time
from pathlib import Path

import pyarrow.parquet as pq

import datavault
import models

VAULT_TABLES = ["hub_customer", "hub_product", "hub_order", "link_order_customer", "link_order_line",
                "sat_customer", "sat_product", "sat_order", "sat_order_line"]
STAR_TABLES = ["dim_customer", "dim_product", "dim_date", "fact_sales"]
# 「月 × 都道府県 × カテゴリの売上」が読む列 (表 -> 列)
QUERY_COLUMNS = {
    "star": {"fact_sales": ["customer_key", "product_key", "date_key", "status", "amount"],
             "dim_customer": ["customer_key", "prefecture"], "dim_product": ["product_key", "category"],
             "dim_date": ["date_key", "month"]},
    "obt": {"obt_sales": ["month", "prefecture", "category", "status", "amount"]},
    "vault": {"sat_order": ["hk_order", "load_dts", "status", "ordered_at"],
              "link_order_customer": ["hk_order", "hk_customer"],
              "sat_customer": ["hk_customer", "load_dts", "prefecture"],
              "link_order_line": ["hk_link", "hk_order", "hk_product"],
              "sat_order_line": ["hk_link", "load_dts", "quantity", "unit_price"],
              "sat_product": ["hk_product", "load_dts", "category"]},
}


def timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


def median_seconds(con, sql, repeat=3):
    runs = []
    for _ in range(repeat):
        _, seconds = timed(lambda: con.execute(sql).fetchall())
        runs.append(seconds)
    return statistics.median(runs)


def parquet_columns(con, table, directory):
    """表を Parquet に書き、列ごとの圧縮後のバイト数 {列: バイト} を返します。"""
    path = Path(directory) / f"{table}.parquet"
    con.execute(f"COPY {table} TO '{path}' (FORMAT parquet)")
    meta = pq.ParquetFile(path).metadata
    sizes = {}
    for g in range(meta.num_row_groups):
        for c in range(meta.num_columns):
            col = meta.row_group(g).column(c)
            sizes[col.path_in_schema] = sizes.get(col.path_in_schema, 0) + col.total_compressed_size
    return sizes


def count_rows(con, tables):
    return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}


def build_all(scale):
    """元データを作り、3 つのモデルを順に作って、かかった秒数も返します。"""
    con = models.load_source(scale)
    _, t_star = timed(lambda: models.build_star(con))
    _, t_obt = timed(lambda: models.build_obt(con))
    datavault.create_vault(con)
    _, t_vault = timed(lambda: datavault.load_all(con))
    con.execute(datavault.CURRENT_VIEWS)
    return con, {"star": t_star, "obt": t_obt, "vault": t_vault}


def measure(scale):
    con, build_seconds = build_all(scale)
    rows = {"orders": con.execute("SELECT count(*) FROM orders").fetchone()[0],
            "star": sum(count_rows(con, STAR_TABLES).values()),
            "obt": count_rows(con, ["obt_sales"])["obt_sales"],
            "vault": sum(count_rows(con, VAULT_TABLES).values())}
    queries = {"star": models.REVENUE_STAR, "obt": models.REVENUE_OBT, "vault": datavault.REVENUE_VAULT}
    answers = {k: con.execute(q).fetchall() for k, q in queries.items()}
    query_seconds = {k: median_seconds(con, q) for k, q in queries.items()}
    stored, scanned = {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        for model, tables in [("star", STAR_TABLES), ("obt", ["obt_sales"]), ("vault", VAULT_TABLES)]:
            sizes = {t: parquet_columns(con, t, tmp) for t in tables}
            stored[model] = sum(sum(s.values()) for s in sizes.values())
            scanned[model] = sum(sizes[t][c] for t, cols in QUERY_COLUMNS[model].items() for c in cols)
    return {"scale": scale, "rows": rows, "build_seconds": build_seconds, "query_seconds": query_seconds,
            "stored_bytes": stored, "scanned_bytes": scanned,
            "same_answer": answers["star"] == answers["obt"] == answers["vault"],
            "answer_rows": len(answers["star"])}


def measure_changes(scale, customer_id=100):
    """3 つの変更を各モデルに行い、書き換え・追記した行数と秒数を返します。"""
    con, _ = build_all(scale)
    out = {}
    lines = con.execute("SELECT count(*) FROM obt_sales WHERE customer_id = ?", [customer_id]).fetchone()[0]

    # 変更 1: 顧客 1 人の引っ越し
    def star():
        return con.execute("UPDATE dim_customer SET prefecture = '沖縄' WHERE customer_id = ?",
                           [customer_id]).fetchone()[0]

    def obt():
        return con.execute("UPDATE obt_sales SET prefecture = '沖縄' WHERE customer_id = ?",
                           [customer_id]).fetchone()[0]

    def vault():
        con.execute("UPDATE customers SET prefecture = '沖縄' WHERE customer_id = ?", [customer_id])
        before = con.execute("SELECT count(*) FROM sat_customer").fetchone()[0]
        datavault.load_satellite(con, "sat_customer", "2026-07-01 00:00:00")
        return con.execute("SELECT count(*) FROM sat_customer").fetchone()[0] - before

    out["move_one_customer"] = {m: dict(zip(("rows", "seconds"), timed(f))) for m, f in
                                [("star", star), ("obt", obt), ("vault", vault)]}
    out["lines_of_that_customer"] = lines

    # 変更 2: カテゴリ名の変更 (寝具 → 睡眠用品)
    def star2():
        return con.execute("UPDATE dim_product SET category = '睡眠用品' WHERE category = '寝具'").fetchone()[0]

    def obt2():
        return con.execute("UPDATE obt_sales SET category = '睡眠用品' WHERE category = '寝具'").fetchone()[0]

    def vault2():
        con.execute("UPDATE base_products SET category = '睡眠用品' WHERE category = '寝具'")
        before = con.execute("SELECT count(*) FROM sat_product").fetchone()[0]
        datavault.load_satellite(con, "sat_product", "2026-07-01 00:00:00")
        return con.execute("SELECT count(*) FROM sat_product").fetchone()[0] - before

    out["rename_category"] = {m: dict(zip(("rows", "seconds"), timed(f))) for m, f in
                              [("star", star2), ("obt", obt2), ("vault", vault2)]}

    # 変更 3: 顧客に新しい属性 (会員ランク) を足す
    def star3():
        con.execute("ALTER TABLE dim_customer ADD COLUMN tier VARCHAR")
        return con.execute("UPDATE dim_customer SET tier = CASE WHEN customer_id % 5 = 0 THEN 'gold' ELSE 'regular' END"
                           ).fetchone()[0]

    def obt3():
        con.execute("ALTER TABLE obt_sales ADD COLUMN tier VARCHAR")
        return con.execute("UPDATE obt_sales SET tier = CASE WHEN customer_id % 5 = 0 THEN 'gold' ELSE 'regular' END"
                           ).fetchone()[0]

    def vault3():
        con.execute("CREATE TABLE sat_customer_tier (hk_customer VARCHAR, load_dts TIMESTAMP, tier VARCHAR)")
        return con.execute(
            "INSERT INTO sat_customer_tier SELECT hk_customer, TIMESTAMP '2026-07-01', "
            "CASE WHEN customer_id % 5 = 0 THEN 'gold' ELSE 'regular' END FROM hub_customer").fetchone()[0]

    out["add_attribute"] = {m: dict(zip(("rows", "seconds"), timed(f))) for m, f in
                            [("star", star3), ("obt", obt3), ("vault", vault3)]}
    return out


def rows_csv(scales=(1, 10, 100)):
    """行数の表 (data/tables/a06-case-rows.csv の中身) を作ります。行数は毎回同じ値になります。"""
    lines = ["規模,注文数,スター (全表の行数),OBT (行数),Data Vault (全表の行数)"]
    for s in scales:
        con, _ = build_all(s)
        r = {"orders": con.execute("SELECT count(*) FROM orders").fetchone()[0],
             "star": sum(count_rows(con, STAR_TABLES).values()), "obt": count_rows(con, ["obt_sales"])["obt_sales"],
             "vault": sum(count_rows(con, VAULT_TABLES).values())}
        lines.append(f"{s} 倍,{r['orders']},{r['star']},{r['obt']},{r['vault']}")
    return "\n".join(lines) + "\n"


PIT_QUERY_COLUMNS = {
    "pit_line": ["hk_link", "hk_order", "hk_product", "hk_customer", "so_dts", "sc_dts", "sl_dts", "sp_dts"],
    "sat_order": ["hk_order", "load_dts", "status", "ordered_at"],
    "sat_customer": ["hk_customer", "load_dts", "prefecture"],
    "sat_order_line": ["hk_link", "load_dts", "quantity", "unit_price"],
    "sat_product": ["hk_product", "load_dts", "category"],
}


def measure_vault_flavors(scale):
    """Data Vault の「素のまま」と「実運用の形」を比べます。

    varchar: ハッシュキーを 32 文字の文字列で持ち、最新の行を window 関数のビューで選ぶ (この章の既定)
    binary: ハッシュキーを 16 バイトの BLOB で持つ
    binary + PIT: さらに、各キーの最新の load_dts を持つ PIT テーブル (明細単位) を作り、等結合だけで読む
    """
    out = {}
    for name, flavor, use_pit in [("varchar", "varchar", False), ("binary", "binary", False),
                                  ("binary_pit", "binary", True)]:
        con = models.load_source(scale)
        datavault.create_vault(con, flavor)
        _, t_load = timed(lambda: datavault.load_all(con, flavor=flavor))
        con.execute(datavault.CURRENT_VIEWS)
        t_pit = 0.0
        if use_pit:
            _, t_pit = timed(lambda: con.execute(datavault.PIT_SQL))
        query = datavault.REVENUE_PIT if use_pit else datavault.REVENUE_VAULT
        answer = con.execute(query).fetchall()
        tables = VAULT_TABLES + (["pit_line"] if use_pit else [])
        with tempfile.TemporaryDirectory() as tmp:
            sizes = {t: parquet_columns(con, t, tmp) for t in tables}
        cols = PIT_QUERY_COLUMNS if use_pit else QUERY_COLUMNS["vault"]
        out[name] = {"load_seconds": round(t_load, 3), "pit_seconds": round(t_pit, 3),
                     "query_seconds": round(median_seconds(con, query), 4),
                     "stored_bytes": sum(sum(s.values()) for s in sizes.values()),
                     "scanned_bytes": sum(sizes[t][c] for t, cs in cols.items() for c in cs),
                     "answer_rows": len(answer)}
        out[name]["_answer"] = answer
    same = out["varchar"]["_answer"] == out["binary"]["_answer"] == out["binary_pit"]["_answer"]
    for v in out.values():
        del v["_answer"]
    out["same_answer"] = same
    return out


def star_scd2_move(scale, customer_id=100):
    """スターのディメンションを SCD2 にしたとき、顧客 1 人の引っ越しで動く行数 (閉じる 1 行 + 足す 1 行) を数えます。"""
    con, _ = build_all(scale)
    con.execute("""CREATE TABLE dim_customer_scd2 AS
        SELECT *, DATE '2026-01-01' AS valid_from, CAST(NULL AS DATE) AS valid_to, true AS is_current FROM dim_customer""")
    closed = con.execute("UPDATE dim_customer_scd2 SET valid_to = DATE '2026-07-01', is_current = false "
                         "WHERE customer_id = ? AND is_current", [customer_id]).fetchone()[0]
    added = con.execute("""INSERT INTO dim_customer_scd2
        SELECT (SELECT max(customer_key) FROM dim_customer_scd2) + 1, customer_id, name, '沖縄',
               DATE '2026-07-01', NULL, true
        FROM dim_customer_scd2 WHERE customer_id = ? AND valid_to = DATE '2026-07-01'""", [customer_id]).fetchone()[0]
    return {"closed": closed, "added": added, "rows_touched": closed + added}


def vault_view_joins():
    """新しい属性 (会員ランク) を新しいサテライトにすると、読む側のビューの結合が何本増えるかを数えます。"""
    base = [ln for ln in datavault.CURRENT_VIEWS.split(";") if "CREATE VIEW v_sales" in ln][0]
    extended = base + "\nLEFT JOIN sat_customer_tier st ON st.hk_customer = hc.hk_customer"
    return {"joins_before": base.count("JOIN"), "joins_after": extended.count("JOIN")}
