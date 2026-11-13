"""3 章のシェルと Git の例を実際に動かし、本文に写した出力と一致することを確かめます。"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "expected"
# 並び順やメッセージが環境の言語設定で変わらないよう、C ロケールで動かす。
ENV = {**os.environ, "LC_ALL": "C", "TZ": "UTC"}

NEEDS_JQ = pytest.mark.skipif(shutil.which("jq") is None, reason="jq が必要です")


def run(script, *args, cwd=None):
    return subprocess.run(
        ["bash", script, *args], cwd=cwd or HERE, env=ENV,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)


@pytest.mark.parametrize("name", [
    "01_files", "02_pipes", "04_exit_codes", "05_env_secrets", "05_permissions",
    "06_timezone", "07_git_flow", "08_git_secret", "exercises",
    pytest.param("03_jq", marks=NEEDS_JQ),
])
def test_output_matches_book(name):
    result = run(f"{name}.sh")
    assert result.returncode == 0, result.stdout
    assert result.stdout == (EXPECTED / f"{name}.txt").read_text(encoding="utf-8")


def test_all_scripts_parse():
    for script in HERE.glob("*.sh"):
        assert subprocess.run(["bash", "-n", str(script)]).returncode == 0, script.name


def test_daily_report_writes_csv(tmp_path):
    out = tmp_path / "reports"
    result = run("daily_report.sh", str(HERE / "access.log"), str(out))
    assert result.returncode == 0, result.stdout
    lines = (out / "errors.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "path,errors"
    assert sum(int(line.split(",")[1]) for line in lines[1:]) == 15
    assert [p.name for p in out.iterdir()] == ["errors.csv"]  # 一時ファイルが残らない


def test_daily_report_without_arguments_fails():
    result = run("daily_report.sh")
    assert result.returncode != 0
    assert "使い方" in result.stdout


def test_daily_report_failure_leaves_no_file(tmp_path):
    out = tmp_path / "reports"
    result = run("daily_report.sh", str(tmp_path / "missing.log"), str(out))
    assert result.returncode != 0
    assert list(out.iterdir()) == []  # 本番の名前のファイルも、一時ファイルも残らない


def test_crontab_has_five_time_fields():
    entries = [ln for ln in (HERE / "crontab.example").read_text(encoding="utf-8").splitlines()
               if ln and not ln.startswith("#") and "=" not in ln.split()[0]]
    assert len(entries) == 1
    minute, hour, day, month, weekday, command = entries[0].split(maxsplit=5)
    assert (minute, hour) == ("15", "3")
    assert command.startswith("/opt/neboske/bin/daily_report.sh")


def test_ssh_config_example_has_host_block():
    text = (HERE / "ssh_config.example").read_text(encoding="utf-8")
    assert text.startswith("Host neboske-batch")
    assert "IdentitiesOnly yes" in text
