"""本物の Spark (Structured Streaming) で、stream_sim.SAMPLE と同じ 6 件を 1 ファイルずつ流します。

ファイル 1 つが 1 件、ファイルの更新時刻 (mtime) が到着の順番です。`maxFilesPerTrigger=1` なので、
Spark は 1 件ずつのマイクロバッチを作ります。窓の出力は foreachBatch で記録します。
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stream_sim import SAMPLE  # noqa: E402


def run(sample=SAMPLE, lateness_s=10, size_s=60):
    """[(バッチ番号, 入力の event_time, そのバッチの開始時のウォーターマーク, 出力した (窓の開始, 件数))] を返します。"""
    from pyspark.sql import SparkSession, functions as F

    work = Path(tempfile.mkdtemp())
    src = work / "in"
    src.mkdir()
    for i, (event_time, arrival) in enumerate(sample):
        f = src / f"e{i:03d}.json"
        f.write_text(json.dumps({"event_time": event_time}))
        os.utime(f, (1_000_000 + arrival, 1_000_000 + arrival))  # 更新時刻で到着の順を決める
    base = SparkSession.builder.master("local[1]").appName("a04-walk").config("spark.ui.enabled", "false").getOrCreate()
    spark = base.newSession()  # 設定を他の利用者と分けるため、新しいセッションを使います
    spark.conf.set("spark.sql.shuffle.partitions", "1")
    spark.sparkContext.setLogLevel("ERROR")
    log = []

    def record(df, batch_id):
        rows = sorted((r["start"], r["n"]) for r in
                      df.select(F.col("window.start").cast("long").alias("start"), F.col("n")).collect())
        log.append((batch_id, rows))

    stream = (spark.readStream.schema("event_time long").option("maxFilesPerTrigger", 1).json(str(src))
              .withColumn("ts", F.col("event_time").cast("timestamp"))
              .withWatermark("ts", f"{lateness_s} seconds")
              .groupBy(F.window("ts", f"{size_s} seconds")).agg(F.count("*").alias("n")))
    query = (stream.writeStream.outputMode("append").foreachBatch(record)
             .option("checkpointLocation", str(work / "ckpt")).trigger(availableNow=True).start())
    query.awaitTermination()
    shutil.rmtree(work, ignore_errors=True)
    return sorted(log)


if __name__ == "__main__":
    for batch_id, rows in run():
        print(f"バッチ {batch_id}: 出力 {rows}")
