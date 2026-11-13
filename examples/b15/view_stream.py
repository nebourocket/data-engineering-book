"""ねぼすけ商店の閲覧イベントを Kafka API のトピック (Redpanda) に流し、コンシューマーで DuckDB に集めます。

Redpanda は Kafka API 互換のブローカーです。ここで使う confluent-kafka (librdkafka) のコードは、
Apache Kafka にそのままつないでも動きます。
"""
import json
import sys
import time
from pathlib import Path

import duckdb
from confluent_kafka import OFFSET_BEGINNING, Consumer, KafkaError, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.common.neboske_shop import generate  # noqa: E402


def make_stream_events(n=200, resend=5):
    """閲覧 (view) イベントを n 件選び、2026-07-01 09:00 から 1.5 秒おきに event_time を振り直します。
    元の event_time は半年に散らばっていて、分ごとの集計が 1 件ずつになるためです (デモ用の加工)。
    最後に先頭の resend 件をもう一度送ります (プロデューサーの再送で起きる重複を真似ます)。"""
    views = [e for e in generate()["events"] if e["event_type"] == "view"]
    seen, picked = set(), []
    for e in views:
        if e["event_id"] not in seen:
            seen.add(e["event_id"])
            picked.append(e)
        if len(picked) == n:
            break
    stream = []
    for i, e in enumerate(picked):
        seconds = int(i * 1.5)
        stream.append({"event_id": e["event_id"], "customer_id": e["customer_id"],
                       "event_type": "view",
                       "event_time": f"2026-07-01 09:{seconds // 60:02d}:{seconds % 60:02d}"})
    return stream + [dict(e) for e in stream[:resend]]


def create_topic(bootstrap, name, partitions=3):
    """トピックを作ります。この手元の 1 台構成ではレプリカ数は 1 しか選べません。"""
    admin = AdminClient({"bootstrap.servers": bootstrap})
    futures = admin.create_topics([NewTopic(name, num_partitions=partitions, replication_factor=1)])
    futures[name].result(timeout=30)


def produce_events(bootstrap, topic, events):
    """customer_id をキーにして送ります。届いた先の (event_id, パーティション, オフセット) を返します。
    返る順は、送った順とは限りません (確認が返ってくる順です)。"""
    producer = Producer({"bootstrap.servers": bootstrap, "enable.idempotence": True})
    placed = []

    def on_delivery(err, msg, event_id):
        if err is not None:
            raise KafkaException(err)
        placed.append((event_id, msg.partition(), msg.offset()))

    for event in events:
        producer.produce(topic, key=str(event["customer_id"]), value=json.dumps(event).encode("utf-8"),
                         on_delivery=lambda err, msg, eid=event["event_id"]: on_delivery(err, msg, eid))
        producer.poll(0)
    producer.flush(30)
    return placed


def open_sink(path=":memory:"):
    """送り先のテーブルを用意します。events_sink は event_id で上書きする (重複しない) 表、
    naive_counts は届くたびに 1 足すだけの表 (重複に弱い、比べるための悪い例) です。"""
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE IF NOT EXISTS events_sink (
            event_id INTEGER PRIMARY KEY, customer_id INTEGER, event_type VARCHAR,
            event_time TIMESTAMP, src_partition INTEGER, src_offset BIGINT)""")
    con.execute("CREATE TABLE IF NOT EXISTS naive_counts (minute TIMESTAMP PRIMARY KEY, views INTEGER)")
    return con


def handle(con, msg):
    """1 件を処理します。event_id が同じなら同じ行を上書きするだけなので、何度届いても結果が変わりません。"""
    event = json.loads(msg.value())
    con.execute("""
        INSERT INTO events_sink VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (event_id) DO UPDATE SET customer_id = excluded.customer_id,
            event_type = excluded.event_type, event_time = excluded.event_time,
            src_partition = excluded.src_partition, src_offset = excluded.src_offset
    """, [event["event_id"], event["customer_id"], event["event_type"], event["event_time"],
          msg.partition(), msg.offset()])
    con.execute("""
        INSERT INTO naive_counts VALUES (date_trunc('minute', CAST(? AS TIMESTAMP)), 1)
        ON CONFLICT (minute) DO UPDATE SET views = views + 1
    """, [event["event_time"]])


def consume(bootstrap, topic, group_id, con, commit=True, expected=None, idle_seconds=6.0):
    """トピックを読んで con に入れ、処理した件数を返します。
    commit=True なら、処理が終わってからオフセットを確定します (処理 → コミットの順)。
    expected 件を処理したか、idle_seconds の間 1 件も来なければ終わります。"""
    consumer = Consumer({
        "bootstrap.servers": bootstrap, "group.id": group_id,
        "auto.offset.reset": "earliest",  # このグループの確定済みオフセットが無いときは、先頭から読む
        "enable.auto.commit": False,  # 自動コミットはしない。処理が済んでから自分でコミットする
    })
    consumer.subscribe([topic])
    processed, last_message = 0, time.monotonic()
    try:
        while time.monotonic() - last_message < idle_seconds:
            if expected is not None and processed >= expected:
                break
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())
            handle(con, msg)
            processed += 1
            last_message = time.monotonic()
            if commit and processed % 50 == 0:
                consumer.commit(asynchronous=False)
        if commit and processed:  # 何も読んでいないときは確定するオフセットが無い
            consumer.commit(asynchronous=False)
    finally:
        consumer.close()
    return processed


def minute_counts(con):
    """events_sink から分ごとの閲覧数を作ります (集計はいつでも作り直せる)。"""
    return con.execute("""
        SELECT date_trunc('minute', event_time) AS minute, count(*) AS views
        FROM events_sink GROUP BY minute ORDER BY minute
    """).fetchall()


def read_partition(bootstrap, topic, partition):
    """1 つのパーティションを先頭から最後まで読み、[(オフセット, キー, イベント)] を返します。
    グループには入らず (assign)、オフセットのコミットもしません。"""
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": "inspect", "enable.auto.commit": False,
                         "enable.partition.eof": True})  # 末尾に着いたら _PARTITION_EOF が届く
    try:
        consumer.assign([TopicPartition(topic, partition, OFFSET_BEGINNING)])
        rows = []
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    return rows
                raise KafkaException(msg.error())
            rows.append((msg.offset(), msg.key().decode("utf-8"), json.loads(msg.value())))
    finally:
        consumer.close()


def group_assignments(bootstrap, topic, group_id, timeout=30.0):
    """同じグループのコンシューマーを 1 つずつ参加させ、割り当てが変わる (リバランス) 様子を返します。
    戻り値は [(参加したコンシューマーの数, [それぞれの担当パーティション番号の一覧])] です。"""
    config = {"bootstrap.servers": bootstrap, "group.id": group_id, "auto.offset.reset": "earliest"}
    consumers, history = [], []
    try:
        for _ in range(2):
            consumers.append(Consumer(config))
            consumers[-1].subscribe([topic])
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                for c in consumers:
                    c.poll(0.5)
                owned = [sorted(tp.partition for tp in c.assignment()) for c in consumers]
                if all(owned) and (len(consumers) == 1 or sum(len(o) for o in owned) == 3):
                    break
            history.append((len(consumers), owned))
        return history
    finally:
        for c in consumers:
            c.close()


def committed_total(bootstrap, topic, group_id, partitions=3):
    """グループがコミット済みのオフセットを、全パーティションぶん足して返します (未コミットは 0 として数えます)。
    トピックに入っている件数と同じなら、読み残し (ラグ) は 0 です。"""
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": group_id, "enable.auto.commit": False})
    try:
        offsets = consumer.committed([TopicPartition(topic, p) for p in range(partitions)], timeout=10)
        return sum(tp.offset for tp in offsets if tp.offset >= 0)  # 未コミットは負の特別な値で返る
    finally:
        consumer.close()
