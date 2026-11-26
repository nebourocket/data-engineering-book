"""第 7 章（準備編）の例を動かし、本文に写した出力が本物かを確かめます。"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PATH": "/usr/bin:/bin"}
sys.path.insert(0, str(HERE))


def run(script):
    r = subprocess.run([sys.executable, str(HERE / script)], cwd=HERE, env=ENV, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    return r.stdout


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 実行結果が、本文に写した ```text の中にそのまま入っているかを確かめるための組
OUTPUTS = {
    "s07_wide_long.py": [
        "{'product': 'アイマスク', 'month': 'jan', 'quantity': 12}",
        "{'product': '置き時計', 'month': 'mar', 'quantity': 5}",
        "2 行 -> 6 行",
    ],
    "s07_csv_quote.py": [
        '1001,アイマスク,"ギフト用, のし付き"',
        '1002,置き時計,"「""静か""な音」希望"',
        "4 ['1001', 'アイマスク', '\"ギフト用', ' のし付き\"']",
        "1 ['2行目\"']",
        "3 ['1003', 'コーヒー豆', '1行目\\n2行目']",
    ],
    "s07_csv_encoding.py": [
        "e6 b3 a8", "ef bb bf", "['\\ufeff注文番号', '商品']", "['注文番号', '商品']", "UnicodeDecodeError",
    ],
    "s07_csv_types.py": [
        "[('00123', 'VARCHAR'), ('04567', 'VARCHAR')]", "[(123, 'INTEGER'), (4567, 'INTEGER')]",
        "2026-03-04", "2026-04-03",
    ],
    "s07_json_basics.py": [
        "{'order_id': 1001, 'paid': True, 'coupon': None, 'items': ['アイマスク', '置き時計']}",
        "dict int bool NoneType list",
        '\\u30a2\\u30a4\\u30de\\u30b9\\u30af',
    ],
    "s07_flatten.py": ["4 件の注文", "7 行の表", "'prefecture': '東京', 'coupon': None"],
    "s07_three_views.py": ["1001,佐藤 太郎,", "1002,鈴木 花子,WELCOME", '"coupon": null}', "│     1001 │ 佐藤 太郎 │ NULL    │"],
    "s07_orders_sql.py": [
        "│ 佐藤 太郎 │   9700 │", "│ 高橋 健   │   3300 │", "│ 鈴木 花子 │   1200 │",
        "│ コーヒー豆 │      4 │", "│ 置き時計   │      1 │", "[(7, 4)]",
    ],
}


@pytest.mark.parametrize("script", list(OUTPUTS))
def test_output(script):
    out = run(script)
    for piece in OUTPUTS[script]:
        assert piece in out, (script, piece)


def test_hand_calculation():
    """手計算: 佐藤 1500x2+2200+1200x3+900=9700、高橋 1500+900x2=3300、鈴木 1200。"""
    data = _load("s07_flatten")
    import json
    rows = data.flatten(json.loads((HERE / "s07_shop_orders.json").read_text(encoding="utf-8")))
    totals = {}
    for r in rows:
        totals[r["customer"]] = totals.get(r["customer"], 0) + r["price"] * r["quantity"]
    assert totals == {"佐藤 太郎": 9700, "鈴木 花子": 1200, "高橋 健": 3300}


def test_tables_match_code(tmp_path):
    make = _load("s07_make_tables")
    make.write_all(tmp_path)
    for name in make.build():
        assert (tmp_path / f"{name}.csv").read_text(encoding="utf-8") == (
            ROOT / "data" / "tables" / f"{name}.csv").read_text(encoding="utf-8"), name


def test_exercises():
    ex = _load("s07_exercises")
    long_rows = _load("s07_wide_long").long_rows
    assert ex.answer1(long_rows) == {"jan": 16, "feb": 15, "mar": 20}
    assert ex.answer2() == '1001,アイマスク,"ギフト用, のし付き"\n'
    assert ex.answer3() == "大阪"
    assert ex.answer4() == [1002]
    flat = _load("s07_flatten")
    import json
    rows = flat.flatten(json.loads((HERE / "s07_shop_orders.json").read_text(encoding="utf-8")))
    con = duckdb.connect()
    con.execute("CREATE TABLE order_items (order_id INTEGER, customer VARCHAR, prefecture VARCHAR,"
                " coupon VARCHAR, product VARCHAR, price INTEGER, quantity INTEGER)")
    con.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?, ?)", [tuple(r.values()) for r in rows])
    sql = (HERE / "s07_exercises.sql").read_text(encoding="utf-8").split("\n", 1)[1]
    assert con.execute(sql).fetchall() == [("大阪", 1, 1200), ("東京", 3, 13000)]
    # 解答の注意書き: count(*) だと東京は 6 (行の数)
    assert con.execute("SELECT count(*) FROM order_items WHERE prefecture = '東京'").fetchall() == [(6,)]
