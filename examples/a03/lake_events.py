"""ねぼすけ商店の閲覧イベントを、小さなバッチに分けて作ります (同じ引数なら同じ結果)。"""
import random

import pyarrow as pa

SCHEMA = pa.schema([
    pa.field("event_id", pa.int64()),
    pa.field("customer_id", pa.int64()),
    pa.field("event_type", pa.string()),
    pa.field("region", pa.string()),
])
EVENT_TYPES = ["view", "view", "view", "add_to_cart", "search", "purchase"]
REGIONS = ["east", "west"]


def make_batch(batch_no, rows=50):
    """batch_no 番目のバッチ。event_id は全バッチを通して重ならない連番です。"""
    rng = random.Random(batch_no)
    start = batch_no * rows
    return pa.table({
        "event_id": list(range(start, start + rows)),
        "customer_id": [rng.randrange(1, 500) for _ in range(rows)],
        "event_type": [rng.choice(EVENT_TYPES) for _ in range(rows)],
        "region": [rng.choice(REGIONS) for _ in range(rows)],
    }, schema=SCHEMA)
