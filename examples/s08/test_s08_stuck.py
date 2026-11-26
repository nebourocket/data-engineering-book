"""第 8 章（準備編）のエラーの例を動かし、出力を確かめます。"""
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PATH": "/usr/bin:/bin"}


def run(script):
    r = subprocess.run([sys.executable, "-I", f"examples/s08/{script}"], cwd=ROOT, env=ENV,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", check=False)
    # 本文では読者のフォルダを /home/taro/nebosuke と書くので、実際の場所をそれに置き換えます。
    return r.returncode, r.stdout.replace(str(ROOT), "/home/taro/nebosuke")


LAST_LINES = {
    "s08_trace.py": "KeyError: 'マグカップ'",
    "s08_err_file.py": "FileNotFoundError: [Errno 2] No such file or directory: 'orders.csv'",
    "s08_err_import.py": "ModuleNotFoundError: No module named 'duckdbb'",
    "s08_err_index.py": "IndexError: list index out of range",
    "s08_err_attribute.py": "AttributeError: 'str' object has no attribute 'uper'. Did you mean: 'upper'?",
    "s08_err_json.py": "json.decoder.JSONDecodeError: Expecting value: line 1 column 46 (char 45)",
    "s08_err_port.py": "OSError: [Errno 98] Address already in use",
    "s08_err_duckdb.py": "_duckdb.CatalogException: Catalog Error: Table with name product does not exist!",
    "s08_ex_range.py": "IndexError: list index out of range",
    "s08_ex_ai.py": "AttributeError: 'str' object has no attribute 'read'",
}


@pytest.mark.parametrize("script", list(LAST_LINES))
def test_error_message(script):
    code, out = run(script)
    assert code == 1
    assert LAST_LINES[script] in out


def test_trace_full():
    code, out = run("s08_trace.py")
    assert out.splitlines()[0] == "3000"
    for piece in ('File "/home/taro/nebosuke/examples/s08/s08_trace.py", line 12, in <module>',
                  'File "/home/taro/nebosuke/examples/s08/s08_trace.py", line 6, in make_receipt',
                  'File "/home/taro/nebosuke/examples/s08/s08_trace.py", line 2, in find_price'):
        assert piece in out


def test_bug_story():
    assert run("s08_bug_before.py") == (0, "900\n")
    code, out = run("s08_bug_prints.py")
    assert out == "price = 1500 total = 1500\nprice = 2200 total = 2200\nprice = 900 total = 900\n900\n"
    assert run("s08_bug_fixed.py") == (0, "4600\n")
    assert sum([1500, 2200, 900]) == 4600
    assert run("s08_minimal.py") == (0, "None\n[900, 1500, 2200]\n")


def test_exercise_answers():
    assert run("s08_ex_range_fixed.py") == (0, "0 アイマスク\n1 置き時計\n2 マグカップ\n")
    assert run("s08_ex_average.py") == (0, "1150.0\n")
    assert run("s08_ex_average_fixed.py") == (0, "1533.3333333333333\n")
    assert 4600 / 3 == 1533.3333333333333
    assert run("s08_ex_ai_fixed.py") == (0, "1001\n")
