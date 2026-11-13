"""取り込み: ねぼすけ商店の表を landing に置き (Parquet)、DuckDB の raw 表に読み込みます。

置き場所の決まり:  raw/dt=<取り込み日>/<表名>.parquet と、全部置き終えた印の raw/dt=<取り込み日>/_SUCCESS。
 - 同じ dt で何度実行しても、同じキーを上書きするだけ (冪等)。
 - 印 (_SUCCESS) は最後に置く。読む側は印が無い dt を読まない (書きかけを読まない)。
 - raw 表は、元の値を加工せずに入れる (表記ゆれや重複も、そのまま)。直すのは次の変換の仕事。
"""
import io
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.common.neboske_shop import generate  # noqa: E402

TABLES = ["orders", "order_items", "events"]


def land(store, dt):
    """TABLES を Parquet にして置き、最後に _SUCCESS を置きます。"""
    data = generate()
    for name in TABLES:
        buf = io.BytesIO()
        pq.write_table(pa.Table.from_pylist(data[name]), buf)
        store.put(f"raw/dt={dt}/{name}.parquet", buf.getvalue())
    store.put(f"raw/dt={dt}/_SUCCESS", b"")


def load_raw(con, store, dt):
    """_SUCCESS のある dt だけを、DuckDB の raw 表 (main スキーマ) に読み込みます。件数の辞書を返します。"""
    if not store.exists(f"raw/dt={dt}/_SUCCESS"):
        raise RuntimeError(f"dt={dt} は _SUCCESS が無いので読みません (書きかけかもしれません)")
    counts = {}
    for name in TABLES:
        table = pq.read_table(io.BytesIO(store.get(f"raw/dt={dt}/{name}.parquet")))
        con.register("_t", table)
        con.execute(f"CREATE OR REPLACE TABLE main.{name} AS SELECT * FROM _t")
        con.unregister("_t")
        counts[name] = table.num_rows
    return counts
