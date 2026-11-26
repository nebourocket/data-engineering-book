"""Kafka (Redpanda) でつなぐ: イベント時刻つきで送る・グループで読んで遅れを測る・トランザクション。"""
import json
import time
import uuid

from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from stream_sim import Event

# シミュレータの 0 秒を 2026-07-01 00:00 UTC に対応させます (時刻 0 は「未設定」と区別がつかないため)
BASE_EPOCH = 1_782_864_000


def new_topic(bootstrap, prefix="a04"):
    """1 パーティションのトピックを作ります (順序をそろえるため)。名前は実行ごとに変えます。"""
    name = f"{prefix}-{uuid.uuid4().hex[:8]}"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    admin.create_topics([NewTopic(name, num_partitions=1, replication_factor=1)])[name].result(timeout=30)
    return name


def delete_topic(bootstrap, name):
    """使い終わったトピックを消します (ブローカーのパーティション数には上限があるため)。"""
    admin = AdminClient({"bootstrap.servers": bootstrap})
    admin.delete_topics([name])[name].result(timeout=30)


def produce_events(bootstrap, topic, events):
    """event_time を Kafka のメッセージ時刻 (ミリ秒) に入れて送ります。届いた時刻 (arrival) は本文に持たせます。"""
    producer = Producer({"bootstrap.servers": bootstrap})
    for e in events:
        body = json.dumps({"id": e.event_id, "category": e.category, "arrival": e.arrival})
        producer.produce(topic, key=str(e.event_id), value=body, timestamp=(BASE_EPOCH + e.event_time) * 1000)
    producer.flush(30)


def read_events(bootstrap, topic, count, group, isolation="read_committed"):
    """count 件を読み、Event に戻します。コミットは呼び出し側が決めるので、ここでは自動コミットを切ります。"""
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": group, "auto.offset.reset": "earliest",
                         "enable.auto.commit": False, "isolation.level": isolation})
    consumer.subscribe([topic])
    events, idle = [], 0
    while len(events) < count and idle < 6:  # グループへの参加に数秒かかるので、何回か待ちます
        msg = consumer.poll(2)
        if msg is None:
            idle += 1
            continue
        if msg.error():
            raise KafkaException(msg.error())
        body = json.loads(msg.value())
        events.append(Event(body["id"], body["category"], msg.timestamp()[1] // 1000 - BASE_EPOCH, body["arrival"]))
    consumer.close()
    return events


def consumer_lag(bootstrap, topic, group, commit_after):
    """先頭から commit_after 件目までコミットしたグループの遅れ (ラグ) = 末尾のオフセット - コミット済みのオフセット。"""
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": group, "enable.auto.commit": False})
    partition = TopicPartition(topic, 0, commit_after)
    consumer.commit(offsets=[partition], asynchronous=False)
    for attempt in range(5):  # 接続の立ち上がりで一度失敗することがあるので、数回やり直します
        try:
            _, high = consumer.get_watermark_offsets(TopicPartition(topic, 0), timeout=10)
            break
        except KafkaException:
            if attempt == 4:
                raise
            time.sleep(1)
    committed = consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset
    consumer.close()
    return high, committed, high - committed


def transaction_demo(bootstrap, topic):
    """コミットした 3 件と、中止した 2 件を送り、読み方 (isolation.level) による見え方の違いを返します。"""
    producer = Producer({"bootstrap.servers": bootstrap, "transactional.id": f"tx-{uuid.uuid4().hex[:8]}"})
    producer.init_transactions(30)
    producer.begin_transaction()
    for i in range(3):
        producer.produce(topic, value=f"commit-{i}")
    producer.commit_transaction(30)
    producer.begin_transaction()
    for i in range(2):
        producer.produce(topic, value=f"abort-{i}")
    producer.flush(30)
    producer.abort_transaction(30)
    return {iso: count_messages(bootstrap, topic, iso) for iso in ("read_uncommitted", "read_committed")}


def count_messages(bootstrap, topic, isolation):
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": f"count-{uuid.uuid4().hex[:6]}",
                         "auto.offset.reset": "earliest", "isolation.level": isolation})
    consumer.subscribe([topic])
    seen, idle = [], 0
    while idle < 3:
        msg = consumer.poll(2)
        if msg is None:
            idle += 1
        elif not msg.error():
            seen.append(msg.value().decode())
    consumer.close()
    return len(seen)
