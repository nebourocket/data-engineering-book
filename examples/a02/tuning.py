"""第2章 Spark の性能調整: 本文のコード。python tuning.py で全部の出力を順に出します。"""
import re
import statistics
import sys
import time
import tempfile
from pathlib import Path

from pyspark.sql import SparkSession, functions as F

sys.path.insert(0, str(Path(__file__).parent.parent / "a01"))
from shopgen import make_events  # noqa: E402
from sparkstat import conf, measure  # noqa: E402
from demo import plan_text  # noqa: E402,F401  (第1章の demo.py)

AQE_OFF = {"spark.sql.adaptive.enabled": "false"}
AQE_ON = {"spark.sql.adaptive.enabled": "true", "spark.sql.adaptive.coalescePartitions.parallelismFirst": "false"}
NO_BROADCAST = {"spark.sql.autoBroadcastJoinThreshold": "-1", "spark.sql.adaptive.autoBroadcastJoinThreshold": "-1"}


def bench(spark, make_df, repeat=3):
    """同じ条件で 1 回ならし運転をしてから repeat 回動かし、(秒数の中央値, 最後のステージの数字) を返します。出力は noop (書かない) 形式です。"""
    times, stats = [], None
    for i in range(repeat + 1):
        df = make_df()
        t, stats = measure(spark, lambda: df.write.format("noop").mode("overwrite").save())
        if i > 0:  # 最初の 1 回 (JVM やファイルの暖機) は捨てる
            times.append(t)
    return statistics.median(times), stats


def balance(records):
    """reduce タスクごとの読み込み行数の (最大, 中央値)。最大が中央値の何倍かが偏りの目安です。"""
    return max(records), int(statistics.median(records))


def make_users(spark, n=50_000):
    """顧客マスタ。n 行で、会員ランクを持ちます。"""
    return (
        spark.range(n).withColumnRenamed("id", "user_id")
        .withColumn("user_id", F.col("user_id").cast("int"))
        .withColumn("rank", F.concat(F.lit("rank_"), (F.col("user_id") % 5).cast("string")))
    )


def make_skewed_events(spark, n, hot_share=0.5, users=50_000):
    """user_id = 0 の「ボット」が hot_share の割合を占める行動ログ。"""
    base = make_events(spark, n, users=users)
    return base.withColumn("user_id", F.when(F.rand(99) < hot_share, F.lit(0)).otherwise(F.col("user_id")))


def skew_ratio(df, cols, parts=16):
    """cols で parts 個に振り分けたときの、最大の行数 / 平均の行数。1 に近いほど均等です。"""
    sizes = (
        df.repartition(parts, *cols).groupBy(F.spark_partition_id().alias("p")).count().collect()
    )
    counts = [r["count"] for r in sizes] + [0] * (parts - len(sizes))
    return round(max(counts) / (sum(counts) / parts), 2)


def aqe_coalesce(spark, events):
    """分割数 200 のまま、AQE を切った場合と入れた場合で、最後のステージのタスク数を比べます。"""
    out = {}
    for label, aqe in [("off", AQE_OFF), ("on", AQE_ON)]:
        with conf(spark, {**aqe, "spark.sql.shuffle.partitions": "200"}):
            agg = events.groupBy("product_id").agg(F.sum("amount").alias("total"))
            _, stats = measure(spark, agg.collect)
            out[label] = (stats[-1]["tasks"], "coalesced" in plan_text(agg))
    return out


def aqe_join_switch(spark, events, users_path):
    """絞り込んだ小さな表との結合を、実行の途中で SortMergeJoin から BroadcastHashJoin へ切り替えます。"""
    with conf(spark, {**AQE_ON, "spark.sql.autoBroadcastJoinThreshold": "100KB"}):
        users = spark.read.parquet(users_path).filter("user_id < 100")
        joined = events.join(users, "user_id")
        before = "SortMergeJoin" in plan_text(joined) and "isFinalPlan=false" in plan_text(joined)
        joined.collect()
        after = "BroadcastHashJoin" in plan_text(joined) and "isFinalPlan=true" in plan_text(joined)
    return before, after


def salting_table(spark):
    """salting_toy の前後を、科目ごとの 1 行にそろえた表 (見出しつきの行のリスト) にします。"""
    before, after = salting_toy(spark)
    rows = [["科目", "札なしの枚数", "札 0 の枚数", "札 1 の枚数"]]
    for subject, n in before.items():
        rows.append([subject, n, after.get(f"{subject}#0", 0), after.get(f"{subject}#1", 0)])
    return rows


def write_salting_table(spark, path):
    """salting_table を CSV に書きます (本文の表の元になるファイル)。"""
    import csv
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(salting_table(spark))


def broadcast_estimate(spark, events, users_path):
    """小さい表の見積もりの大きさ (explain cost の出力) とファイルの大きさを並べ、しきい値を下げると配られなくなることを確かめます。"""
    users = spark.read.parquet(users_path)
    estimate = re.search(r"sizeInBytes=([\d.]+ \w+)", plan_text(users, "cost")).group(1)
    file_bytes = sum(f.stat().st_size for f in Path(users_path).glob("*.parquet"))
    out = {"estimate": estimate, "file_bytes": file_bytes}
    for label, threshold in [("default_broadcast", "10485760"), ("half_file_size_broadcast", str(file_bytes // 2))]:
        with conf(spark, {**AQE_OFF, "spark.sql.autoBroadcastJoinThreshold": threshold}):
            out[label] = "BroadcastHashJoin" in plan_text(events.join(users, "user_id"))
    return out


def salted_join(events, users, salts):
    """偏ったキーの結合: 大きい側にランダムな salt を付け、小さい側は salt の数だけ複製します。"""
    spread = events.withColumn("salt", (F.rand(7) * salts).cast("int"))
    copies = users.withColumn("salt", F.explode(F.sequence(F.lit(0), F.lit(salts - 1))))
    return spread.join(copies, ["user_id", "salt"]).drop("salt")


def skew_join_fixes(spark, events, users, salts=8):
    """素の結合・ソルティング・AQE の偏り対策を、結合ステージのタスク数と reduce タスクの (最大, 中央値) 行数で比べます。"""
    def join_stage(df):
        _, st = measure(spark, lambda: df.write.format("noop").mode("overwrite").save())
        return st[-1]["tasks"], *balance(st[-1]["task_read_records"])

    out = {}
    plain = {**NO_BROADCAST, "spark.sql.shuffle.partitions": "16"}
    plain_join = events.join(users, "user_id").select("event_id", "rank")
    with conf(spark, {**AQE_OFF, **plain}):
        out["plain"] = (*join_stage(plain_join), plain_join.count())
        out["ratio_before"] = skew_ratio(events, ["user_id"])
        salted = salted_join(events, users, salts).select("event_id", "rank")
        out["salted"] = (*join_stage(salted), salted.count())
        out["ratio_after"] = skew_ratio(events.withColumn("salt", (F.rand(7) * salts).cast("int")), ["user_id", "salt"])
    aqe = {**AQE_ON, **plain, "spark.sql.adaptive.coalescePartitions.enabled": "false",
           "spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes": "256KB",
           "spark.sql.adaptive.advisoryPartitionSizeInBytes": "256KB"}
    with conf(spark, aqe):
        out["aqe"] = (*join_stage(plain_join), plain_join.count())
    return out


def groupby_skew_needs_no_salt(spark, events):
    """sum は部分集計で小さくなるので、偏ったキーでも reduce タスクの読む量は偏りません。collect_list は部分結果が小さくならず、読む量が偏ります。"""
    def reduce_balance(agg):
        _, st = measure(spark, lambda: agg.write.format("noop").mode("overwrite").save())
        return st[0]["shuffle_write_records"], balance(st[-1]["task_read_records"]), balance(st[-1]["task_read_bytes"])

    with conf(spark, {**AQE_OFF, "spark.sql.shuffle.partitions": "16"}):
        summed = reduce_balance(events.groupBy("user_id").agg(F.sum("amount")))
        listed = reduce_balance(events.groupBy("user_id").agg(F.collect_list("amount")))
    return {"input_ratio": skew_ratio(events, ["user_id"]), "sum": summed, "collect_list": listed}


def salting_toy(spark):
    """10 枚の答案のうち 5 枚が「数学」。salt を足すと、数学の束が 2 つに分かれます。"""
    subjects = ["math"] * 5 + ["art", "music", "pe", "history", "science"]
    sheets = spark.createDataFrame([(s, i % 2) for i, s in enumerate(subjects)], ["subject", "salt"])
    before = {r["subject"]: r["count"] for r in sheets.groupBy("subject").count().collect()}
    after = {f'{r["subject"]}#{r["salt"]}': r["count"] for r in sheets.groupBy("subject", "salt").count().collect()}
    return dict(sorted(before.items())), dict(sorted(after.items()))


def count_files(path):
    """Parquet ファイルの数を数えます。"""
    return len(list(Path(path).rglob("*.parquet")))


def small_file_writes(spark, events, root):
    """同じデータを、書き方を変えて 5 通りに書き、ファイル数を数えます。"""
    dated = events.select("event_id", "event_date", "amount")
    variants = {
        "plain": dated,
        "repartition_by_date": dated.repartition("event_date"),
        "repartition_1": dated.repartition(1, "event_date"),
        "repartition_4": dated.repartition(4, "event_date"),
    }
    out = {}
    with conf(spark, AQE_OFF):
        for name, df in variants.items():
            df.write.mode("overwrite").partitionBy("event_date").parquet(f"{root}/{name}")
            out[name] = count_files(f"{root}/{name}")
        with conf(spark, {"spark.sql.files.maxRecordsPerFile": "2000"}):
            variants["repartition_by_date"].write.mode("overwrite").partitionBy("event_date").parquet(f"{root}/capped")
            out["capped_2000_rows"] = count_files(f"{root}/capped")
    return out


def partitions_for(total_mb, target_mb=128):
    """書き出すデータの大きさ (MB) と、1 ファイルの目安の大きさ (MB) から、書く前のパーティション数を決めます。"""
    return max(1, round(total_mb / target_mb))


def coalesce_limits_parallelism(spark, events):
    """重い列を足したあとに coalesce(1) と repartition(1) を使い、各ステージのタスク数を比べます。"""
    heavy = events.withColumn("h", F.sha2(F.col("event_id").cast("string"), 256))
    out = {}
    with conf(spark, AQE_OFF):
        for label, df in [("coalesce", heavy.coalesce(1)), ("repartition", heavy.repartition(1))]:
            _, st = measure(spark, lambda: df.write.format("noop").mode("overwrite").save())
            out[label] = [s["tasks"] for s in st]
    return out


def read_many_files(spark, events, root, counts=(4, 200)):
    """同じデータを counts 個のファイルで書き、読んで集計するのにかかる秒数を比べます。"""
    out = {}
    for n in counts:
        events.repartition(n).write.mode("overwrite").parquet(f"{root}/f{n}")
        sec, _ = bench(spark, lambda: spark.read.parquet(f"{root}/f{n}").agg(F.sum("amount")), repeat=3)
        out[n] = round(sec, 2)
    return out


def cache_effect(spark, path, rounds):
    """sha2 を rounds 回重ねた列 (作るのが重い列) を持つ表で、キャッシュの有無による計画と秒数を比べます。"""
    def twice(df):
        df.groupBy("product_id").agg(F.max("h")).collect()
        df.groupBy("user_id").agg(F.max("h")).collect()

    def table():
        digest = F.col("event_id").cast("string")
        for _ in range(rounds):
            digest = F.sha2(digest, 256)
        return spark.read.parquet(path).withColumn("h", digest)

    def one_use_with_cache():
        cached = table().cache()
        start = time.perf_counter()
        cached.groupBy("product_id").agg(F.max("h")).collect()  # 載せる費用を含む 1 回目
        seconds = time.perf_counter() - start
        cached.unpersist()
        return seconds

    with conf(spark, AQE_OFF):
        heavy = table()
        plain_two = bench_twice(spark, lambda: twice(heavy))
        plain_one = bench_twice(spark, lambda: heavy.groupBy("product_id").agg(F.max("h")).collect())
        cached = table().cache()
        twice(cached)  # 最初のアクションで、キャッシュに載る
        cached_two = bench_twice(spark, lambda: twice(cached))
        executed = plan_text(cached.groupBy("product_id").agg(F.max("h"))).split("InMemoryRelation")[0]
        reads_file = {"plain": "FileScan" in plan_text(heavy.groupBy("product_id").agg(F.max("h"))),
                      "cached": "FileScan" in executed}
        cached.unpersist()
        one_use_with_cache()  # ならし運転
        cached_one = statistics.median(one_use_with_cache() for _ in range(3))
    return {"two_uses": (round(plain_two, 2), round(cached_two, 2)),
            "one_use": (round(plain_one, 2), round(cached_one, 2)), "reads_file": reads_file}


def bench_twice(spark, action, repeat=3):
    """action() をならし運転 1 回のあと repeat 回動かし、秒数の中央値を返します。"""
    measure(spark, action)
    return statistics.median(measure(spark, action)[0] for _ in range(repeat))


def band_python(use_arrow):
    """金額の帯を返す Python UDF。use_arrow=False は行ごとに呼ぶ従来の形、True は Arrow で受け渡す形です。"""
    return F.udf(lambda amount: "high" if amount >= 5000 else "low", "string", useArrow=use_arrow)


def band_pandas():
    """同じ処理の pandas UDF (列のまとまりを pandas の Series で受け取ります)。"""
    import pandas as pd

    @F.pandas_udf("string")
    def band(amount: pd.Series) -> pd.Series:
        return amount.ge(5000).map({True: "high", False: "low"})

    return band


def band_builtin():
    """同じ処理を組み込み関数で書いたもの。"""
    return F.when(F.col("amount") >= 5000, "high").otherwise("low")


def udf_vs_builtin(spark, events):
    """同じ列を 4 通りで作り、計画に出る演算子・結果の一致・相対的な秒数を比べます。"""
    makers = {
        "builtin": lambda: band_builtin(),
        "python_classic": lambda: band_python(False)("amount"),
        "python_arrow": lambda: band_python(True)("amount"),
        "pandas": lambda: band_pandas()("amount"),
    }
    out, reference = {}, None
    for name, make in makers.items():
        df = events.withColumn("band", make())
        operator = re.search(r"\w*EvalPython", plan_text(df))
        counts = sorted((r["band"], r["count"]) for r in df.groupBy("band").count().collect())
        reference = reference or counts
        seconds, _ = bench(spark, lambda: events.withColumn("band", make()).groupBy("band").count())
        out[name] = (operator.group(0) if operator else "なし", counts == reference, round(seconds, 2))
    base = out["builtin"][2]
    return {k: (*v, round(v[2] / base, 1)) for k, v in out.items()}


def pushdown_lost(spark, path):
    """UDF で絞り込むと、Parquet へ押し込まれる条件が消えます。"""
    is_high = F.udf(lambda amount: amount >= 5000, "boolean", useArrow=False)
    events = spark.read.parquet(path)
    builtin = re.search(r"PushedFilters: \[(.*?)\]", plan_text(events.filter(F.col("amount") >= 5000)))
    udf = re.search(r"PushedFilters: \[(.*?)\]", plan_text(events.filter(is_high("amount"))))
    return builtin.group(1), udf.group(1)


def executor_memory_layout(executor_memory_mb, overhead_factor=0.10, overhead_min_mb=384,
                           fraction=0.6, storage_fraction=0.5, reserved_mb=300):
    """エグゼキュータ 1 つのメモリの内訳 (MB)。設定の既定値を引数にしてあります。"""
    overhead = max(int(executor_memory_mb * overhead_factor), overhead_min_mb)
    usable = executor_memory_mb - reserved_mb
    unified = usable * fraction
    return {
        "heap": executor_memory_mb,
        "reserved": reserved_mb,
        "usable": usable,
        "unified": round(unified, 1),
        "storage_protected": round(unified * storage_fraction, 1),
        "user": round(usable * (1 - fraction), 1),
        "overhead": overhead,
        "container": executor_memory_mb + overhead,
    }


def format_memory(layout):
    """内訳を、層ごとの表にして文字列で返します。"""
    rows = [
        ("ヒープ spark.executor.memory", layout["heap"]),
        ("  予約 (固定)", layout["reserved"]),
        ("  使える分 = ヒープ - 予約", layout["usable"]),
        ("    統合メモリ = 使える分 x 0.6", layout["unified"]),
        ("      うち保存の保護枠 = 統合 x 0.5", layout["storage_protected"]),
        ("    ユーザーメモリ = 使える分 x 0.4", layout["user"]),
        ("overhead (ヒープの外)", layout["overhead"]),
        ("コンテナの大きさ = ヒープ + overhead", layout["container"]),
    ]
    return "\n".join(f"{name:<40}{mb:>9,.1f} MB" for name, mb in rows)


def unified_memory_in_this_jvm(spark):
    """手元の JVM で、式 (ヒープ - 300MB) x 0.6 と Spark の報告する値を比べます (MB)。
    _jvm と _jsc は PySpark の内部の入口です。公開された API ではないので、学習用に限ります。"""
    sc = spark.sparkContext
    heap_mb = sc._jvm.java.lang.Runtime.getRuntime().maxMemory() / 1024 / 1024
    reported_bytes = sc._jsc.sc().getExecutorMemoryStatus().valuesIterator().next()._1()  # (保存に使える最大, 空き)
    return round(executor_memory_layout(heap_mb)["unified"], 1), round(reported_bytes / 1024 / 1024, 1)


def write_job(spark, events, users, out_dir, builtin, by_date):
    """ケーススタディの 1 回分: 顧客と結合し、金額の帯を付け、日付ごとに書く。"""
    band = band_builtin() if builtin else band_python(True)("amount")
    df = events.join(users, "user_id").withColumn("band", band)
    if by_date:
        df = df.repartition("event_date")
    df.select("event_id", "event_date", "rank", "band", "amount").write.mode("overwrite").partitionBy("event_date").parquet(out_dir)


def case_study(spark, root, n, repeat=3):
    """偏り + Python UDF + 小さいファイルを、1 つずつ直して比べます (ならし運転 1 回のあと repeat 回の中央値)。"""
    make_skewed_events(spark, n).write.mode("overwrite").parquet(f"{root}/events")
    make_users(spark).coalesce(1).write.mode("overwrite").parquet(f"{root}/users")
    variants = [
        ("A 元のまま", NO_BROADCAST, False, False),
        ("B UDF を組み込みへ", NO_BROADCAST, True, False),
        ("C 書く前に日付で整える", NO_BROADCAST, True, True),
        ("D 顧客を配る", {}, True, True),
    ]
    rows = []
    for label, extra, builtin, by_date in variants:
        with conf(spark, {**AQE_OFF, **extra, "spark.sql.shuffle.partitions": "16"}):
            times, stats = [], None
            for i in range(repeat + 1):
                events = spark.read.parquet(f"{root}/events")
                users = spark.read.parquet(f"{root}/users")
                t, stats = measure(spark, lambda: write_job(spark, events, users, f"{root}/out", builtin, by_date))
                if i > 0:
                    times.append(t)
            heaviest = max(stats, key=lambda s: max(s["task_read_records"]))
            rows.append({
                "variant": label,
                "tasks": sum(s["tasks"] for s in stats),
                "shuffle_mb": round(sum(s["shuffle_write_bytes"] for s in stats) / 1e6, 1),
                "max_reduce_rows": max(heaviest["task_read_records"]),
                "median_reduce_rows": int(statistics.median(heaviest["task_read_records"])),
                "files": count_files(f"{root}/out"),
                "seconds": statistics.median(times),
            })
    for r in rows:
        r["relative"] = round(r["seconds"] / rows[0]["seconds"], 2)
    return rows


def format_case(rows):
    """ケーススタディの結果を、桁をそろえた表にして文字列で返します。"""
    lines = [f"{'variant':<22}{'tasks':>6}{'shuffle MB':>11}{'max rows':>10}{'median':>8}{'files':>6}{'seconds':>8}{'relative':>9}"]
    for r in rows:
        lines.append(
            f"{r['variant']:<22}{r['tasks']:>6}{r['shuffle_mb']:>11}{r['max_reduce_rows']:>10}"
            f"{r['median_reduce_rows']:>8}{r['files']:>6}{r['seconds']:>8.1f}{r['relative']:>9}"
        )
    return "\n".join(lines)


def build_session():
    return (
        SparkSession.builder.master("local[2]").appName("a02")
        .config("spark.sql.shuffle.partitions", "4").config("spark.default.parallelism", "4")
        .config("spark.ui.enabled", "false").config("spark.ui.showConsoleProgress", "false")
        .config("spark.driver.bindAddress", "127.0.0.1").getOrCreate()
    )


if __name__ == "__main__":
    spark = build_session()
    spark.sparkContext.setLogLevel("ERROR")
    events = make_events(spark, 200_000).cache()
    skewed = make_skewed_events(spark, 1_000_000).cache()
    users = make_users(spark)
    with tempfile.TemporaryDirectory() as tmp:
        events.write.parquet(f"{tmp}/events")
        users.coalesce(1).write.parquet(f"{tmp}/users")
        print("coalesce:", aqe_coalesce(spark, events))
        print("join switch:", aqe_join_switch(spark, events, f"{tmp}/users"))
        print("salting toy:", salting_toy(spark))
        print("broadcast estimate:", broadcast_estimate(spark, events, f"{tmp}/users"))
        print("skew ratio:", skew_ratio(events, ["user_id"]), skew_ratio(skewed, ["user_id"]))
        print("skew fixes:", skew_join_fixes(spark, skewed, users))
        print("groupby skew:", groupby_skew_needs_no_salt(spark, skewed))
        print("files:", small_file_writes(spark, events, f"{tmp}/w"))
        print("partitions_for:", partitions_for(10_000), partitions_for(50), partitions_for(300))
        print("coalesce limits:", coalesce_limits_parallelism(spark, events))
        print("read many:", read_many_files(spark, events, f"{tmp}/m"))
        print("cache:", {r: cache_effect(spark, f"{tmp}/events", r) for r in (1, 50)})
        print("udf:", udf_vs_builtin(spark, events))
        print("pushdown:", pushdown_lost(spark, f"{tmp}/events"))
        print("memory 8g:", executor_memory_layout(8192))
        print(format_memory(executor_memory_layout(8192)))
        print("memory jvm:", unified_memory_in_this_jvm(spark))
        print(format_case(case_study(spark, f"{tmp}/case", 1_000_000)))
