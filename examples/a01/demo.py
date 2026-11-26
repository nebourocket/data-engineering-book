"""第1章 分散処理の内側: 本文のコード。python demo.py で全部の出力を順に出します。"""
import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path

from pyspark.sql import SparkSession, functions as F

sys.path.insert(0, str(Path(__file__).parent))
from shopgen import make_events, make_products  # noqa: E402
from sparkstat import conf, measure, stage_stats  # noqa: E402

NO_AQE = {"spark.sql.adaptive.enabled": "false"}


def plan_text(df, mode="simple"):
    """df.explain(mode) の出力を、文字列として受け取ります。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        df.explain(mode)
    return buf.getvalue()


def exchange_kinds(df):
    """物理計画に出る Exchange の種類を、上から順に返します (BroadcastExchange は別に数えます)。"""
    return re.findall(r"(?<![A-Za-z])Exchange (\w+)", plan_text(df))


def topology(spark):
    """この SparkSession がどこで動いているか (master・既定の並列度) を返します。"""
    sc = spark.sparkContext
    return {"master": sc.master, "parallelism": sc.defaultParallelism}


def stages_of_groupby(spark, events):
    """groupBy 1 回のアクションが、ステージいくつ・タスクいくつに分かれたかを返します。"""
    agg = events.groupBy("event_type").agg(F.sum("amount").alias("total"))
    _, stats = measure(spark, agg.collect)
    return [(s["stage"], s["tasks"], s["shuffle_write_bytes"], s["shuffle_read_bytes"]) for s in stats]


def lazy_demo(spark, events):
    """変換だけでは仕事が走らず、アクションで初めて走ることを、ジョブの数で確かめます。"""
    sc = spark.sparkContext
    sc.setJobGroup("lazy", "lazy demo")
    purchases = events.filter(F.col("event_type") == "purchase").select("user_id", "amount")
    before = len(sc.statusTracker().getJobIdsForGroup("lazy"))
    purchases.count()
    after = len(sc.statusTracker().getJobIdsForGroup("lazy"))
    return before, after


def rows_per_partition(df):
    """パーティションごとの行数を返します (分けて並列に処理する単位)。"""
    return [n for (n,) in df.rdd.glom().map(lambda rows: (len(rows),)).collect()]


def narrow_and_wide(events):
    """狭い変換だけの計画と、広い変換を含む計画で、Exchange の数を比べます。"""
    narrow = events.filter("event_type = 'purchase'").select("user_id", "amount")
    wide = narrow.groupBy("user_id").agg(F.sum("amount").alias("total"))
    return len(exchange_kinds(narrow)), exchange_kinds(wide)


def shuffle_rows(spark, events):
    """集計のキーの種類数で、シャッフルに流れる行数がどう変わるかを測ります。"""
    out = {}
    for key in ["event_type", "user_id"]:
        agg = events.groupBy(key).agg(F.sum("amount"))
        _, stats = measure(spark, agg.collect)
        out[key] = stats[0]["shuffle_write_records"]
    return out


def partial_pairs(events):
    """部分集計のあとに残る行数 = (パーティション, キー) の組の数を数えます。"""
    pairs = events.select(F.spark_partition_id().alias("p"), "event_type").distinct().count()
    return events.rdd.getNumPartitions(), pairs


def exchange_kinds_by_operation(events):
    """操作ごとに、計画に出る Exchange の種類を調べます。"""
    return {
        "groupBy": exchange_kinds(events.groupBy("user_id").count()),
        "orderBy": exchange_kinds(events.orderBy("amount")),
        "repartition": exchange_kinds(events.repartition(8)),
        "count": exchange_kinds(events.agg(F.count("*"))),
    }


def shuffle_partition_effect(spark, events, sizes):
    """spark.sql.shuffle.partitions を変えて、集計後のタスク数と空のパーティション数を数えます。"""
    out = {}
    for n in sizes:
        with conf(spark, {**NO_AQE, "spark.sql.shuffle.partitions": str(n)}):
            agg = events.groupBy("event_type").agg(F.sum("amount").alias("total"))
            _, stats = measure(spark, agg.collect)
            sizes_after = rows_per_partition(agg)
            out[n] = (stats[-1]["tasks"], sum(1 for r in sizes_after if r == 0), stats[0]["shuffle_write_bytes"])
    return out


def input_partitions(spark, path, files):
    """同じ行数をファイル数だけに分けて書き、読んだときのパーティション数 (= タスク数) を返します。"""
    out = {}
    for n in files:
        target = f"{path}/files_{n}"
        spark.range(100_000).repartition(n).write.mode("overwrite").parquet(target)
        out[n] = spark.read.parquet(target).rdd.getNumPartitions()
    return out


def join_strategies(spark, events, products):
    """小さい表との結合で、しきい値を変えると結合の方式がどう変わるかを見ます。"""
    out = {}
    for label, threshold in [("default", "10485760"), ("off", "-1")]:
        with conf(spark, {**NO_AQE, "spark.sql.autoBroadcastJoinThreshold": threshold}):
            joined = events.join(products, "product_id")
            text = plan_text(joined)
            out[label] = {
                "broadcast": "BroadcastHashJoin" in text,
                "sortmerge": "SortMergeJoin" in text,
                "exchanges": len(exchange_kinds(joined)),
            }
    return out


def normalize(plan):
    """式 ID (#12) と plan_id を消して、計画どうしを比べられる形にします。"""
    return re.sub(r"#\d+L?|plan_id=\d+|\[.*?\]", "", plan)


def sql_and_dataframe_plans(spark, events):
    """同じ集計を SQL と DataFrame API で書き、物理計画が同じになることを確かめます。"""
    events.createOrReplaceTempView("events")
    by_sql = spark.sql(
        "SELECT event_date, SUM(amount) AS total FROM events WHERE event_type = 'purchase' GROUP BY event_date"
    )
    by_api = (
        events.filter(F.col("event_type") == "purchase")
        .groupBy("event_date")
        .agg(F.sum("amount").alias("total"))
    )
    return normalize(plan_text(by_sql)) == normalize(plan_text(by_api))


def write_events(spark, path, n, files=8):
    """イベントログを n 行作り、Parquet に書きます。書いた量 (MB) を返します。"""
    make_events(spark, n).repartition(files).write.mode("overwrite").parquet(path)
    return round(sum(f.stat().st_size for f in Path(path).glob("*.parquet")) / 1e6, 1)


def write_products(spark, path):
    """商品マスタを Parquet に書きます。"""
    make_products(spark).coalesce(1).write.mode("overwrite").parquet(path)


def report_job(events, products):
    """ケーススタディの集計: 購入額を、日別・カテゴリ別に足します。"""
    return (
        events.filter(F.col("event_type") == "purchase")
        .join(products, "product_id")
        .groupBy("event_date", "category")
        .agg(F.sum("amount").alias("total"))
    )


def case_study(spark, events_path, products_path, repeat=3):
    """同じ集計を、設定を 1 つずつ変えて動かし、計画と測定値を比べます。"""
    variants = [
        ("A 元の設定", {"spark.sql.autoBroadcastJoinThreshold": "-1", "spark.sql.shuffle.partitions": "200"}),
        ("B しきい値を戻す", {"spark.sql.autoBroadcastJoinThreshold": "10485760", "spark.sql.shuffle.partitions": "200"}),
        ("C 分割数を 8 に", {"spark.sql.autoBroadcastJoinThreshold": "10485760", "spark.sql.shuffle.partitions": "8"}),
    ]
    rows = []
    for label, settings in variants:
        with conf(spark, {**NO_AQE, **settings}):
            events = spark.read.parquet(events_path)
            job = report_job(events, spark.read.parquet(products_path))
            times, stats = [], None
            for _ in range(repeat):
                t, stats = measure(spark, lambda: job.write.format("noop").mode("overwrite").save())
                times.append(t)
            rows.append({
                "variant": label,
                "join": "BroadcastHashJoin" if "BroadcastHashJoin" in plan_text(job) else "SortMergeJoin",
                "exchanges": len(exchange_kinds(job)),
                "stages": len(stats),
                "tasks": sum(s["tasks"] for s in stats),
                "shuffle_write_mb": round(sum(s["shuffle_write_bytes"] for s in stats) / 1e6, 2),
                "seconds": sorted(times)[len(times) // 2],
            })
    base = rows[0]["seconds"]
    for r in rows:
        r["relative"] = round(r["seconds"] / base, 2)
    return rows


def format_case(rows):
    """ケーススタディの結果を、桁をそろえた表にして文字列で返します。"""
    head = f"{'variant':<18}{'join':<20}{'exch':>5}{'stages':>7}{'tasks':>6}{'shuffle MB':>11}{'seconds':>8}{'relative':>9}"
    lines = [head]
    for r in rows:
        lines.append(
            f"{r['variant']:<18}{r['join']:<20}{r['exchanges']:>5}{r['stages']:>7}{r['tasks']:>6}"
            f"{r['shuffle_write_mb']:>11}{r['seconds']:>8.2f}{r['relative']:>9}"
        )
    return "\n".join(lines)


def build_session():
    return (
        SparkSession.builder.master("local[2]").appName("a01")
        .config("spark.sql.shuffle.partitions", "4").config("spark.default.parallelism", "4").config("spark.ui.enabled", "false").config("spark.ui.showConsoleProgress", "false")
        .config("spark.driver.bindAddress", "127.0.0.1").getOrCreate()
    )


if __name__ == "__main__":
    spark = build_session()
    spark.sparkContext.setLogLevel("ERROR")
    events = make_events(spark, 200_000).cache()
    products = make_products(spark)
    with conf(spark, NO_AQE):
        print("topology:", topology(spark))
        print("lazy:", lazy_demo(spark, events))
        print("stages:", stages_of_groupby(spark, events))
        print("partitions:", events.rdd.getNumPartitions(), rows_per_partition(events))
        print("narrow/wide:", narrow_and_wide(events))
        print("shuffle rows:", shuffle_rows(spark, events))
        print("partial pairs:", partial_pairs(events))
        print("exchange kinds:", exchange_kinds_by_operation(events))
        print("shuffle partitions:", shuffle_partition_effect(spark, events, [1, 4, 200]))
        with tempfile.TemporaryDirectory() as tmp:
            print("input partitions:", input_partitions(spark, tmp, [1, 8, 100]))
        print("joins:", join_strategies(spark, events, products))
        print("sql==api:", sql_and_dataframe_plans(spark, events))
    with tempfile.TemporaryDirectory() as tmp:
        mb = write_events(spark, f"{tmp}/events", 2_000_000)
        write_products(spark, f"{tmp}/products")
        print("parquet MB for 2M rows:", mb)
        read = spark.read.parquet
        with conf(spark, NO_AQE):
            job = report_job(read(f"{tmp}/events"), read(f"{tmp}/products"))
            print(plan_text(job, "formatted"))
            with conf(spark, {"spark.sql.autoBroadcastJoinThreshold": "-1"}):
                print(plan_text(report_job(read(f"{tmp}/events"), read(f"{tmp}/products"))))
        print(format_case(case_study(spark, f"{tmp}/events", f"{tmp}/products")))
