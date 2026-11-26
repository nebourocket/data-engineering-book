"""4 章の Python の例を実際に動かし、本文に写した出力と一致することを確かめます。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
# トレースバックの日本語や記号が文字化けしないよう、入出力を UTF-8 にそろえる。
ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PATH": "/usr/bin:/bin"}
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))


def run(case, tmp):
    """ケースのスクリプトを、空のフォルダ tmp の中で動かします（ファイルを書くため）。"""
    for f in case.get("files", []):
        src, _, dst = f.partition(":")
        shutil.copy(HERE / src, tmp / (dst or src))
    script = HERE / case["script"]
    if case.get("as"):
        shutil.copy(script, tmp / case["as"])
        script = tmp / case["as"]
    cmd = [sys.executable] + ([] if case.get("noI") else ["-I"]) + [str(script)] + case.get("args", [])
    r = subprocess.run(
        cmd, cwd=tmp, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", check=False)
    # 本文では読者のフォルダを /home/taro/nebosuke と書くので、実際の場所をそれに置き換えます。
    return r.returncode, r.stdout.replace(str(HERE), "/home/taro/nebosuke").replace(str(tmp), "/home/taro/nebosuke")


@pytest.mark.parametrize("name", sorted(CASES))
def test_output_matches_book(name, tmp_path):
    _, out = run(CASES[name], tmp_path)
    assert out == (HERE / "expected" / f"{name}.txt").read_text(encoding="utf-8")


def test_error_last_lines(tmp_path):
    assert run(CASES["scope"], tmp_path)[1].splitlines()[-1] == "NameError: name 'result' is not defined"
    assert run(CASES["nofile"], tmp_path)[1].splitlines()[-1] == (
        "FileNotFoundError: [Errno 2] No such file or directory: 'nothing.txt'")
    assert run(CASES["nomodule"], tmp_path)[1].splitlines()[-1] == "ModuleNotFoundError: No module named 'polars'"


def test_sales_csv_content(tmp_path):
    assert run(CASES["report"], tmp_path)[0] == 0
    assert (tmp_path / "sales.csv").read_bytes().decode("utf-8").splitlines() == [
        "item,sales", "アイマスク,7500", "マグカップ,2880", "コーヒー豆,4800", "枕,4800"]


def test_bad_rows_are_skipped(tmp_path):
    code, out = run(CASES["report_bad"], tmp_path)
    assert code == 0
    assert out.splitlines()[-1].endswith("(飛ばした注文 2件)")
    assert run(CASES["step3_bad"], tmp_path)[0] == 1


def test_requests_is_installed():
    r = subprocess.run([sys.executable, "-c", "import requests; print(requests.__version__)"],
                       stdout=subprocess.PIPE, text=True, check=True)
    assert r.stdout.strip() == "2.34.2"
