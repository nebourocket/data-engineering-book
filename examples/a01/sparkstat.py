"""Spark UI の Stages タブに出る数字を、コードで取り出す道具です (内部の API を使うので、学習用の道具です)。"""
import itertools
import time
from contextlib import contextmanager

_groups = itertools.count()


def stage_stats(spark, group):
    """ジョブグループ group で動いたステージごとに、タスク数・シャッフル・入力・Spill と、タスクごとの読み込み行数を返します。
    Spark の内部 (statusStore) を py4j 越しに呼ぶ、学習用の道具です。Spark の版が変わると動かなくなることがあります。"""
    sc = spark.sparkContext
    tracker = sc.statusTracker()
    store = sc._jsc.sc().statusStore()
    no_status, no_quantiles = sc._jvm.java.util.ArrayList(), sc._gateway.new_array(sc._jvm.double, 0)
    rows = []
    for job_id in tracker.getJobIdsForGroup(group):
        for stage_id in list(tracker.getJobInfo(job_id).stageIds):
            attempts = store.stageData(stage_id, True, no_status, False, no_quantiles)
            for i in range(attempts.length()):
                s = attempts.apply(i)
                if s.numCompleteTasks() == 0:
                    continue  # 前のジョブの結果を再利用して飛ばしたステージ
                reads, read_bytes, gc_ms, tasks = [], [], 0, s.tasks().get().values().iterator()
                while tasks.hasNext():
                    metrics = tasks.next().taskMetrics().get()
                    reads.append(metrics.shuffleReadMetrics().recordsRead())
                    read_bytes.append(metrics.shuffleReadMetrics().remoteBytesRead() + metrics.shuffleReadMetrics().localBytesRead())
                    gc_ms += metrics.jvmGcTime()
                rows.append({
                    "stage": stage_id,
                    "tasks": s.numTasks(),
                    "input_bytes": s.inputBytes(),
                    "shuffle_write_bytes": s.shuffleWriteBytes(),
                    "shuffle_write_records": s.shuffleWriteRecords(),
                    "shuffle_read_bytes": s.shuffleReadBytes(),
                    "task_read_records": sorted(reads),
                    "task_read_bytes": sorted(read_bytes),
                    "spill_memory_bytes": s.memoryBytesSpilled(),
                    "spill_disk_bytes": s.diskBytesSpilled(),
                    "gc_ms": gc_ms,
                })
    return sorted(rows, key=lambda r: r["stage"])


def measure(spark, action):
    """action() を 1 回動かし、(かかった秒数, ステージごとの数字) を返します。"""
    group = f"measure-{next(_groups)}"
    spark.sparkContext.setJobGroup(group, group)
    start = time.perf_counter()
    action()
    elapsed = time.perf_counter() - start
    return elapsed, stage_stats(spark, group)


@contextmanager
def conf(spark, settings):
    """with ブロックの中だけ設定を変え、出るときに元へ戻します。"""
    old = {k: spark.conf.get(k, None) for k in settings}
    for k, v in settings.items():
        spark.conf.set(k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                spark.conf.unset(k)
            else:
                spark.conf.set(k, v)
