"""1 章のシェル操作を、使い捨ての HOME の中で実際に動かし、本文に写した出力と一致することを確かめます。

docker / WSL / VS Code の手順 (04〜06) はこの環境では動かせないため、構文 (bash -n) だけ確かめます。
"""
import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ENV = {"LC_ALL": "C", "PATH": os.environ["PATH"]}


def run(script, home, cwd=None):
    result = subprocess.run(
        ["bash", str(HERE / script)], cwd=cwd or home, env={**ENV, "HOME": str(home)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    # 本文では読者の家を /home/taro と書くので、使い捨ての HOME をそれに置き換えます。
    return result.returncode, result.stdout.replace(str(home), "/home/taro")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def test_first_commands(home):
    code, out = run("01_first_commands.sh", home)
    assert code == 0
    assert out == (
        "/home/taro/deb-practice\n"  # 空のフォルダの ls は何も出さない
        "memo.txt\n"
        "ねぼすけ商店\n"
        "memo.txt\nnote.txt\n"
        "memo.txt\n")
    assert (home / "deb-practice" / "memo.txt").read_text(encoding="utf-8") == "ねぼすけ商店\n"


def test_paths(home):
    code, out = run("02_paths.sh", home)
    assert code == 0
    assert out == (
        "/home/taro/deb-practice/data\n"
        "/home/taro/deb-practice\n"
        "data\n"
        ".\n..\n.hidden\ndata\n"
        "/home/taro\n"
        "/home/taro\n")


def test_errors(home):
    code, out = run("03_errors.sh", home)
    assert code == 0  # 最後の行が成功するので全体の終了コードは 0
    assert out == (
        "cat: nothing.txt: No such file or directory\n"
        "ls: cannot access '/no/such/folder': No such file or directory\n"
        "最初の行\n")
    assert (home / "memo.txt").read_text(encoding="utf-8") == "あとの行\n"


@pytest.mark.parametrize("script", sorted(p.name for p in HERE.glob("*.sh")))
def test_syntax(script):
    assert subprocess.run(["bash", "-n", str(HERE / script)]).returncode == 0


def test_dockerfile_copy_matches_repo():
    """本文に載せる Dockerfile が、リポジトリ直下の本物と同じであることを確かめます。"""
    assert (HERE / "Dockerfile.book").read_text(encoding="utf-8") == (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_exercises(home):
    code, out = run("exercises.sh", home)
    assert code == 0
    assert out == "/home/taro/deb-practice/shop\nbackup.txt\nアイマスク 1500\n/home/taro/deb-practice\n"
