"""2 章の Python の例を実際に動かし、本文に写した出力と一致することを確かめます。"""
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
# トレースバックの日本語や記号が文字化けしないよう、入出力を UTF-8 にそろえる。
ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PATH": "/usr/bin:/bin"}


def run(script, stdin=""):
    r = subprocess.run(
        [sys.executable, "-I", str(HERE / script)], cwd=HERE, env=ENV, input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", check=False)
    # 本文では読者のフォルダを /home/taro/nebosuke と書くので、実際の場所をそれに置き換えます。
    return r.returncode, r.stdout.replace(str(HERE), "/home/taro/nebosuke")


def test_hello():
    assert run("01_hello.py") == (0, "おはよう、ねぼすけ商店\n")


def test_calc():
    assert run("02_calc.py") == (0, (
        "10\n4\n21\n2.3333333333333335\n2\n1\n1024\n3.75\n5.0\n0.30000000000000004\n14\n20\n"))


def test_shop():
    assert run("03_shop.py") == (0, "3600\n360\n4460\n4\n4800\n")


def test_strings():
    assert run("04_strings.py") == (0, (
        "ねぼすけ商店のアイマスク\n6\nアイマスクを3個、合計4460円です\n1行目\n2行目\n"
        "He said 'good morning'\nNEBOSUKE\nnebosuke\nFalse\nTrue\n"))


def test_types():
    assert run("05_types.py") == (0, (
        "<class 'int'>\n<class 'float'>\n<class 'str'>\n43\n42円\n3.0\n3\n421\n"))


def test_input():
    # input() の案内文は標準出力に出ますが、打った文字は端末が表示するもので、ここには入りません。
    assert run("06_input.py", "ねぼ\n3\n") == (0, "お名前は? 個数は? ねぼさん、3個で3600円です\n")


def test_receipt():
    code, out = run("07_receipt.py", "アイマスク\n1500\n2\n")
    assert code == 0
    assert out == (
        "商品名: 値段(円): 個数: --- ねぼすけ商店 レシート ---\n"
        "アイマスク 1500円 x 2個 = 3000円\n消費税(10%): 300円\n送料: 500円\n合計: 3800円\n")


def test_receipt_rejects_non_number():
    code, out = run("07_receipt.py", "アイマスク\n千五百\n2\n")
    assert code == 1
    assert out.splitlines()[-1] == "ValueError: invalid literal for int() with base 10: '千五百'"


ERRORS = {
    "err_syntax.py": "SyntaxError: unterminated string literal (detected at line 1)",
    "err_name.py": "NameError: name 'totl' is not defined. Did you mean: 'total'?",
    "err_type.py": 'TypeError: can only concatenate str (not "int") to str',
    "err_value.py": "ValueError: invalid literal for int() with base 10: '3個'",
    "err_zero.py": "ZeroDivisionError: division by zero",
    "err_indent.py": "IndentationError: unexpected indent",
}


@pytest.mark.parametrize("script", sorted(ERRORS))
def test_error_last_line(script):
    code, out = run(script)
    assert code == 1
    assert out.splitlines()[-1] == ERRORS[script]


@pytest.mark.skipif(sys.version_info[:2] != (3, 12), reason="エラー表示の細部は Python のバージョンで変わる")
def test_error_full_text_matches_book():
    assert run("err_name.py")[1] == (
        "Traceback (most recent call last):\n"
        '  File "/home/taro/nebosuke/err_name.py", line 2, in <module>\n'
        "    print(totl)\n"
        "          ^^^^\n"
        "NameError: name 'totl' is not defined. Did you mean: 'total'?\n")
    assert run("err_type.py")[1] == (
        "Traceback (most recent call last):\n"
        '  File "/home/taro/nebosuke/err_type.py", line 2, in <module>\n'
        '    print("合計は" + total + "円")\n'
        "          ~~~~~~~~~^~~~~~~\n"
        'TypeError: can only concatenate str (not "int") to str\n')
    assert run("err_syntax.py")[1] == (
        '  File "/home/taro/nebosuke/err_syntax.py", line 1\n'
        '    print("おはよう、ねぼすけ商店)\n'
        "          ^\n"
        "SyntaxError: unterminated string literal (detected at line 1)\n")
    assert run("err_indent.py")[1] == (
        '  File "/home/taro/nebosuke/err_indent.py", line 2\n'
        "    quantity = 3\n"
        "IndentationError: unexpected indent\n")
    assert run("err_value.py")[1] == (
        "Traceback (most recent call last):\n"
        '  File "/home/taro/nebosuke/err_value.py", line 1, in <module>\n'
        '    count = int("3個")\n'
        "            ^^^^^^^^^^\n"
        "ValueError: invalid literal for int() with base 10: '3個'\n")


def test_exercises():
    assert run("ex_answers.py") == (0, "1920\n2\n1\n1100\nアイマスクは1500円です\n7\n34\n")


def test_exercise_input():
    assert run("ex6_input.py", "2000\n") == (0, "税抜きの値段: 2200\n")


def test_repl_session():
    """対話モード (>>>) に打った行を流し込み、本文の例と同じ答えが返ることを確かめます。"""
    r = subprocess.run(
        [sys.executable, "-I", "-i", "-q"], env=ENV, input='x = 5\nx\nprint(x * 2)\n"nebo" + "suke"\n',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", check=False)
    assert r.stdout == ">>> >>> 5\n>>> 10\n>>> 'nebosuke'\n>>> \n"


def test_docker_commands_parse():
    """docker を使う手順は、この環境では動かせないので構文だけ確かめます。"""
    assert subprocess.run(["bash", "-n", str(HERE / "08_run.sh")]).returncode == 0
