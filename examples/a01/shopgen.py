"""ねぼすけ商店のイベントログを、件数を指定して作る生成器です (Spark の乱数は seed を固定しています)。"""
from pyspark.sql import functions as F

EVENT_TYPES = ["view", "view", "view", "view", "cart", "purchase"]


def make_events(spark, n, users=50_000, products=2_000, seed=42):
    """行動ログ n 行。user_id と product_id は一様、種類は view 4 : cart 1 : purchase 1 の割合です。"""
    types = F.array(*[F.lit(t) for t in EVENT_TYPES])
    return (
        spark.range(n)
        .withColumnRenamed("id", "event_id")
        .withColumn("user_id", (F.rand(seed) * users).cast("int"))
        .withColumn("product_id", (F.rand(seed + 1) * products).cast("int"))
        .withColumn("event_type", types[(F.rand(seed + 2) * len(EVENT_TYPES)).cast("int")])
        .withColumn("amount", F.round(F.rand(seed + 3) * 9_000 + 500, 0).cast("int"))
        .withColumn("event_date", F.date_add(F.lit("2026-01-01").cast("date"), (F.rand(seed + 4) * 30).cast("int")))
    )


def make_products(spark, products=2_000):
    """商品マスタ (小さい側の表)。カテゴリは 20 種類です。"""
    return (
        spark.range(products)
        .withColumnRenamed("id", "product_id")
        .withColumn("product_id", F.col("product_id").cast("int"))
        .withColumn("category", F.concat(F.lit("cat_"), (F.col("product_id") % 20).cast("string")))
    )
