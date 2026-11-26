"""大きなディメンションの分け方: 変わりやすい属性をミニディメンションに分けます。"""
import random

LEVELS = {"engagement": 3, "tier": 4}  # 変わりやすい属性 (値の種類)
CHANGE_RATE = {"prefecture": 0.02, "engagement": 0.40, "tier": 0.15}
PREFECTURES = 10


def simulate(n_customers=20000, months=12, seed=9):
    """顧客ごと・月ごとの属性を作り、(属性の組, 開始月) の変わり目の数を返します。"""
    rng = random.Random(seed)
    versions_all = versions_stable = 0
    combos = set()
    for _ in range(n_customers):
        state = {"prefecture": rng.randrange(PREFECTURES), "engagement": rng.randrange(3), "tier": rng.randrange(4)}
        last_all = last_stable = None
        for _ in range(months):
            for attr, rate in CHANGE_RATE.items():
                if rng.random() < rate:
                    state[attr] = rng.randrange(PREFECTURES if attr == "prefecture" else LEVELS[attr])
            combos.add((state["engagement"], state["tier"]))
            row_all = tuple(state.values())
            row_stable = state["prefecture"]
            versions_all += row_all != last_all
            versions_stable += row_stable != last_stable
            last_all, last_stable = row_all, row_stable
    return {"customers": n_customers, "months": months,
            "scd2_rows_all_attributes": versions_all,
            "scd2_rows_stable_only": versions_stable,
            "mini_dimension_rows": len(combos)}


def profile_key_cost(con):
    """ファクトにミニディメンションのキー (profile_key) を 1 列足したときの、Parquet のバイト数の増え方を測ります。

    con は models.build_star を済ませたもの。キーは顧客から決まる 12 通りの値で代用します。
    """
    import tempfile

    import pyarrow.parquet as pq

    def size(sql):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/f.parquet"
            con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet)")
            return pq.ParquetFile(path).metadata.num_rows, sum(
                pq.ParquetFile(path).metadata.row_group(g).column(c).total_compressed_size
                for g in range(pq.ParquetFile(path).metadata.num_row_groups)
                for c in range(pq.ParquetFile(path).metadata.num_columns))

    rows, before = size("SELECT * FROM fact_sales")
    rows2, after = size("SELECT *, customer_key % 12 AS profile_key FROM fact_sales")
    return {"rows": rows, "rows_after": rows2, "bytes_before": before, "bytes_after": after,
            "increase_percent": round((after - before) / before * 100, 1)}
