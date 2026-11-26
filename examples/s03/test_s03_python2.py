"""3 章の Python の例を実際に動かし、本文に写した出力と一致することを確かめます。"""
import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
# トレースバックの日本語や記号が文字化けしないよう、入出力を UTF-8 にそろえる。
ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PATH": "/usr/bin:/bin"}
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))


def run(script, stdin=""):
    r = subprocess.run(
        [sys.executable, "-I", str(HERE / script)], cwd=HERE, env=ENV, input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", check=False)
    # 本文では読者のフォルダを /home/taro/nebosuke と書くので、実際の場所をそれに置き換えます。
    return r.returncode, r.stdout.replace(str(HERE), "/home/taro/nebosuke")


@pytest.mark.parametrize("name", sorted(CASES))
def test_output_matches_book(name):
    case = CASES[name]
    code, out = run(case["script"], case.get("stdin", ""))
    expected = (HERE / "expected" / f"{name}.txt").read_text(encoding="utf-8")
    assert out == expected
    assert (code != 0) == case["script"].startswith("s03_err_")


def test_key_values():
    assert run("s03_03_if.py") == (0, "送料: 500円\n")
    assert run("s03_17_orders.py")[1].splitlines()[2:] == [
        "合計: 15420円", "3000円以上の注文: 3件", "一番高い商品: 枕 (4800円)"]


def test_error_last_lines():
    assert run("s03_err_noindent.py")[1].splitlines()[-1] == (
        "IndentationError: expected an indented block after 'if' statement on line 2")
    assert run("s03_err_keyerror.py")[1].splitlines()[-1] == "KeyError: 'quantity'"
    assert run("s03_err_index.py")[1].splitlines()[-1] == "IndexError: list index out of range"


def test_forever_stops_with_ctrl_c():
    p = subprocess.Popen(
        [sys.executable, "-I", str(HERE / "s03_10_forever.py")], cwd=HERE, env=ENV,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    assert p.stdout.readline() == "1\n"  # 動き出したのを見てから Ctrl+C を送る
    p.send_signal(signal.SIGINT)
    _, err = p.communicate(timeout=10)
    assert p.returncode != 0
    assert err.splitlines()[-1] == "KeyboardInterrupt"
