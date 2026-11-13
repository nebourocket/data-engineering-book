"""第 15 章のコード例のテスト。Redpanda (Kafka API) が要ります。トピック名とグループ名は毎回ユニークにします。"""
import sys
import uuid
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.b15.view_stream import (  # noqa: E402
    committed_total, consume, create_topic, group_assignments, make_stream_events, minute_counts, open_sink,
    produce_events, read_partition)

PARTITIONS = 3


def unique(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def topic(kafka_bootstrap):
    name = unique("test-views")
    create_topic(kafka_bootstrap, name, partitions=PARTITIONS)
    return name


def test_make_stream_events_has_resends():
    events = make_stream_events(n=200, resend=5)
    assert len(events) == 205
    assert len({e["event_id"] for e in events}) == 200
    assert all(e["event_type"] == "view" for e in events)
    assert events[0]["event_time"] == "2026-07-01 09:00:00"


def test_same_key_stays_in_one_partition_and_keeps_order(kafka_bootstrap, topic):
    events = make_stream_events(resend=0)
    placed = produce_events(kafka_bootstrap, topic, events)
    assert len(placed) == len(events)
    seen_partition = {}
    total = 0
    for partition in range(PARTITIONS):
        rows = read_partition(kafka_bootstrap, topic, partition)
        total += len(rows)
        assert [offset for offset, _, _ in rows] == list(range(len(rows)))  # オフセットは 0 から連番
        times = [e["event_time"] for _, _, e in rows]
        assert times == sorted(times)  # パーティションの中は、送った順 (= 時刻順) のまま
        for _, key, _ in rows:
            assert seen_partition.setdefault(key, partition) == partition  # 同じキーは同じパーティション
            # librdkafka の既定 (consistent_random) は、キーの CRC32 をパーティション数で割った余り
            assert zlib.crc32(key.encode("utf-8")) % PARTITIONS == partition
    assert total == len(events)
    assert len(set(seen_partition.values())) == PARTITIONS  # 全パーティションが使われている


def test_commit_after_processing_means_rerun_adds_nothing(kafka_bootstrap, topic):
    events = make_stream_events()
    produce_events(kafka_bootstrap, topic, events)
    sink, group = open_sink(), unique("g")
    assert consume(kafka_bootstrap, topic, group, sink, commit=True, expected=len(events)) == 205
    # 「0 件」がグループ参加の遅れのせいでないことを、ブローカーに記録されたコミット位置で確かめる (ラグ 0)
    assert committed_total(kafka_bootstrap, topic, group) == 205
    assert sink.execute("SELECT count(*) FROM events_sink").fetchone() == (200,)  # 再送 5 件は上書きされた
    assert consume(kafka_bootstrap, topic, group, sink, commit=True, idle_seconds=3) == 0
    assert committed_total(kafka_bootstrap, topic, group) == 205
    assert sink.execute("SELECT count(*) FROM events_sink").fetchone() == (200,)
    # 別のグループ名で読むと先頭から全部届くが、event_id で上書きなので行数は変わらない
    assert consume(kafka_bootstrap, topic, unique("g"), sink, commit=True, expected=len(events)) == 205
    assert sink.execute("SELECT count(*) FROM events_sink").fetchone() == (200,)
    assert minute_counts(sink) == [(m, 40) for m, _ in minute_counts(sink)]
    assert len(minute_counts(sink)) == 5


def test_without_commit_messages_are_redelivered_but_sink_stays_correct(kafka_bootstrap, topic):
    events = make_stream_events()
    produce_events(kafka_bootstrap, topic, events)
    sink, group = open_sink(), unique("g")
    for _ in range(2):
        assert consume(kafka_bootstrap, topic, group, sink, commit=False, expected=len(events)) == 205
        assert committed_total(kafka_bootstrap, topic, group) == 0  # コミットしていないので記録も無い
    assert sink.execute("SELECT count(*) FROM events_sink").fetchone() == (200,)  # event_id で上書きなので増えない
    assert sink.execute("SELECT sum(views) FROM naive_counts").fetchone() == (410,)  # 足し込み方式は 2 倍になる
    assert sum(v for _, v in minute_counts(sink)) == 200


def test_second_consumer_triggers_rebalance(kafka_bootstrap, topic):
    history = group_assignments(kafka_bootstrap, topic, unique("g"))
    (n1, owned1), (n2, owned2) = history
    assert (n1, n2) == (1, 2)
    assert owned1 == [[0, 1, 2]]
    assert sorted(p for o in owned2 for p in o) == [0, 1, 2]  # 重ならず、全部が誰かの担当
    assert all(owned2)
