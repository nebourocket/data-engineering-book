import duckdb
import pyarrow.parquet as pq

from examples.common import neboske_shop as shop


def test_tables_and_sizes():
    d = shop.generate()
    assert set(d) == {"customers", "products", "orders", "order_items", "events"}
    assert 400 <= len(d["customers"]) <= 700
    assert 40 <= len(d["products"]) <= 80
    assert 2000 <= len(d["orders"]) <= 4500


def test_deterministic():
    assert shop.generate(seed=42) == shop.generate(seed=42)
    assert shop.generate(seed=1) != shop.generate(seed=42)


def test_intentional_defects_exist():
    d = shop.generate()
    emails = [c["email"] for c in d["customers"]]
    assert any(e is None for e in emails)
    ids = [e["event_id"] for e in d["events"]]
    assert len(ids) != len(set(ids))  # 重複イベント
    assert any(e["received_at"] > e["event_time"] for e in d["events"])
    assert any(e["received_at"][:10] > e["event_time"][:10] for e in d["events"])  # 遅れて届く


def test_orders_reference_customers():
    d = shop.generate()
    cids = {c["customer_id"] for c in d["customers"]}
    assert all(o["customer_id"] in cids for o in d["orders"])
    oids = {o["order_id"] for o in d["orders"]}
    assert all(i["order_id"] in oids for i in d["order_items"])


def test_write_duckdb(tmp_path):
    p = tmp_path / "shop.duckdb"
    shop.write_duckdb(p)
    con = duckdb.connect(str(p))
    assert con.execute("select count(*) from orders").fetchone()[0] == len(shop.generate()["orders"])
    con.close()


def test_write_parquet(tmp_path):
    shop.write_parquet(tmp_path)
    assert pq.read_table(tmp_path / "customers.parquet").num_rows == len(shop.generate()["customers"])
