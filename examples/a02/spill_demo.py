"""小さいヒープの Spark で、Spill と GC の時間、driver.maxResultSize のエラーを実際に起こします (別プロセスで動かします)。"""
import json
import sys
from pathlib import Path

from pyspark.sql import SparkSession, functions as F

sys.path.insert(0, str(Path(__file__).parent.parent / "a01"))
from sparkstat import measure  # noqa: E402


def small_heap_session(driver_memory):
    """local モードでは、ドライバのヒープが executor のヒープを兼ねます。"""
    return (
        SparkSession.builder.master("local[2]").appName("a02-spill")
        .config("spark.driver.memory", driver_memory).config("spark.driver.maxResultSize", "1m")
        .config("spark.sql.shuffle.partitions", "4").config("spark.sql.adaptive.enabled", "false")
        .config("spark.ui.enabled", "false").config("spark.ui.showConsoleProgress", "false")
        .config("spark.driver.bindAddress", "127.0.0.1").getOrCreate()
    )


def spill_report(spark, rows):
    """1 つのパーティションに集めて並べ替え、Spill (メモリ上の大きさ / ディスク上の大きさ) と GC の時間を返します。"""
    df = spark.range(rows).withColumn("pad", F.sha2(F.col("id").cast("string"), 256)).repartition(1).sortWithinPartitions("pad")
    _, stats = measure(spark, lambda: df.write.format("noop").mode("overwrite").save())
    last = stats[-1]
    return {
        "spill_memory_mb": round(last["spill_memory_bytes"] / 1e6),
        "spill_disk_mb": round(last["spill_disk_bytes"] / 1e6),
        "gc_ms": last["gc_ms"],
    }


def max_result_size_error(spark):
    """collect で 1 MB の上限を超え、ジョブが中止されるときのメッセージの先頭を返します。"""
    try:
        spark.range(200_000).withColumn("pad", F.sha2(F.col("id").cast("string"), 256)).collect()
    except Exception as e:  # noqa: BLE001
        lines = [l for l in str(e).split("\n") if "maxResultSize" in l]
        return lines[0].strip()[:300] if lines else "別のエラー"
    return "エラーなし"


if __name__ == "__main__":
    spark = small_heap_session(sys.argv[1])
    spark.sparkContext.setLogLevel("ERROR")
    print(json.dumps({"heap": sys.argv[1], **spill_report(spark, int(sys.argv[2])),
                      "max_result_size_error": max_result_size_error(spark)}, ensure_ascii=False))
