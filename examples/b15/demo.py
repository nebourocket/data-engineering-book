"""第 15 章の通しの実行例。Redpanda (Kafka API) に閲覧イベントを流して、読み方の違いを順に見せます。

  KAFKA_BOOTSTRAP=localhost:19092 python examples/b15/demo.py
"""
import os
import sys
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.b15.view_stream import (  # noqa: E402
    committed_total, consume, create_topic, group_assignments, make_stream_events, minute_counts, open_sink,
    produce_events, read_partition)


def main(bootstrap):
    topic = f"neboske-views-{uuid.uuid4().hex[:8]}"  # 実行ごとに別のトピックにして、前回の残りと混ざらないようにする
    create_topic(bootstrap, topic, partitions=3)
    events = make_stream_events()
    placed = produce_events(bootstrap, topic, events)
    per_partition = Counter(partition for _, partition, _ in placed)
    print("トピック:", topic)
    print("送った件数:", len(placed), "パーティションごと:", dict(sorted(per_partition.items())))

    print("--- パーティションの中の並び (先頭 3 件) ---")
    for partition in range(3):
        rows = read_partition(bootstrap, topic, partition)
        print(f"partition {partition}:", [(offset, key, e["event_time"][-5:]) for offset, key, e in rows[:3]])

    print("--- コミットしない読み方 (コミットの前に落ちたのと同じ) ---")
    sink = open_sink()
    group = f"no-commit-{uuid.uuid4().hex[:6]}"
    for run in (1, 2):
        n = consume(bootstrap, topic, group, sink, commit=False, expected=len(events))
        rows, = sink.execute("SELECT count(*) FROM events_sink").fetchone()
        naive, = sink.execute("SELECT sum(views) FROM naive_counts").fetchone()
        print(f"{run} 回目: 処理 {n} 件 / events_sink {rows} 行 / 足し込み方式の合計 {naive}")

    print("--- 処理してからコミットする読み方 ---")
    group = f"with-commit-{uuid.uuid4().hex[:6]}"
    print("グループ:", group)
    for run in (1, 2):
        n = consume(bootstrap, topic, group, sink, commit=True, expected=len(events), idle_seconds=4)
        rows, = sink.execute("SELECT count(*) FROM events_sink").fetchone()
        done = committed_total(bootstrap, topic, group)
        print(f"{run} 回目: 処理 {n} 件 / events_sink {rows} 行 / コミット済みの位置の合計 {done} (送った件数 {len(events)})")

    print("--- 分ごとの閲覧数 (events_sink から作る) ---")
    for minute, views in minute_counts(sink):
        print(minute.strftime("%H:%M"), views)

    print("--- 同じグループに 2 つ目が入ったとき ---")
    for joined, owned in group_assignments(bootstrap, topic, f"rebalance-{uuid.uuid4().hex[:6]}"):
        print(f"コンシューマー {joined} つ: 担当 {owned}")


if __name__ == "__main__":
    main(os.environ.get("KAFKA_BOOTSTRAP", "localhost:19092"))
