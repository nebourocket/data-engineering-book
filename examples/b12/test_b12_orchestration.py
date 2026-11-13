"""第 12 章のコードを動かして、冪等・再実行・バックフィル・依存の順序を確かめます。"""
import ast
import csv
import importlib.util
import sys
import types
from graphlib import CycleError
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def _load(name, path=None):
    spec = importlib.util.spec_from_file_location(name + "_b12", path or HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


job = _load("daily_job")
runner = _load("mini_runner")
make_source = _load("make_source")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source" / "sales.csv"
    make_source.write_sales(path)
    return path


def read_day(out, day):
    with (out / "daily_sales" / f"date={day}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_process_writes_one_row_per_category(source, tmp_path):
    out = tmp_path / "out"
    assert job.process("2026-03-05", source, out) == 5
    rows = read_day(out, "2026-03-05")
    assert {r["category"]: int(r["revenue"]) for r in rows} == {
        "寝具": 16000, "朝食": 84750, "目覚まし": 16550, "雑貨": 20100, "飲み物": 119750}
    assert {r["date"] for r in rows} == {"2026-03-05"}


def test_rerun_gives_identical_file(source, tmp_path):
    out = tmp_path / "out"
    target = out / "daily_sales" / "date=2026-03-05.csv"
    job.process("2026-03-05", source, out)
    first = target.read_bytes()
    job.process("2026-03-05", source, out)
    job.process("2026-03-05", source, out)
    assert target.read_bytes() == first
    assert sorted(p.name for p in target.parent.iterdir()) == ["date=2026-03-05.csv"]  # 一時ファイルが残らない


def test_rerun_replaces_instead_of_appending(source, tmp_path):
    out = tmp_path / "out"
    job.process("2026-03-05", source, out)
    before = sum(int(r["revenue"]) for r in read_day(out, "2026-03-05"))
    # 遅れて届いた明細（雑貨 1,000 円 × 2）が元データに足された、という想定
    with source.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([99999, "2026-03-05 23:59:59", "placed", "雑貨", 2, 1000])
    job.process("2026-03-05", source, out)
    rows = read_day(out, "2026-03-05")
    assert len(rows) == 5  # 行は増えない（置き換え）
    assert sum(int(r["revenue"]) for r in rows) == before + 2000
    assert {r["category"]: int(r["orders"]) for r in rows}["雑貨"] == 6


def test_other_days_are_untouched(source, tmp_path):
    out = tmp_path / "out"
    job.process("2026-03-04", source, out)
    other = (out / "daily_sales" / "date=2026-03-04.csv").read_bytes()
    job.process("2026-03-05", source, out)
    job.process("2026-03-05", source, out)
    assert (out / "daily_sales" / "date=2026-03-04.csv").read_bytes() == other


def test_backfill_covers_range_and_is_repeatable(source, tmp_path):
    out = tmp_path / "out"
    result = job.backfill("2026-03-01", "2026-03-07", source, out)
    assert list(result) == [f"2026-03-0{d}" for d in range(1, 8)]
    snapshot = {p.name: p.read_bytes() for p in (out / "daily_sales").iterdir()}
    assert len(snapshot) == 7
    job.backfill("2026-03-03", "2026-03-05", source, out)  # 一部だけやり直しても、全体は変わらない
    assert {p.name: p.read_bytes() for p in (out / "daily_sales").iterdir()} == snapshot


def test_day_without_orders_writes_header_only(source, tmp_path):
    out = tmp_path / "out"
    assert job.process("2026-01-01", source, out) == 0  # ねぼすけ商店の最初の注文は 1 月 4 日
    assert read_day(out, "2026-01-01") == []
    header = (out / "daily_sales" / "date=2026-01-01.csv").read_text(encoding="utf-8").strip()
    assert header == "date,category,orders,revenue"


def test_failure_keeps_previous_file(source, tmp_path, monkeypatch):
    out = tmp_path / "out"
    job.process("2026-03-05", source, out)
    target = out / "daily_sales" / "date=2026-03-05.csv"
    good = target.read_bytes()

    def boom(*args):
        raise OSError("disk full")

    monkeypatch.setattr(job.os, "replace", boom)
    with pytest.raises(OSError):
        job.process("2026-03-05", source, out)
    assert target.read_bytes() == good
    assert sorted(p.name for p in target.parent.iterdir()) == ["date=2026-03-05.csv"]


@pytest.mark.parametrize("bad", ["2026-3-5", "20260305", "", "2026-02-30"])
def test_bad_day_is_rejected_before_writing(source, tmp_path, bad):
    with pytest.raises(ValueError):
        job.process(bad, source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_days_between_is_inclusive_and_ordered():
    assert job.days_between("2026-02-27", "2026-03-02") == ["2026-02-27", "2026-02-28", "2026-03-01", "2026-03-02"]
    assert job.days_between("2026-03-05", "2026-03-05") == ["2026-03-05"]
    with pytest.raises(ValueError):
        job.days_between("2026-03-05", "2026-03-04")


def test_source_has_day(source, tmp_path):
    assert job.source_has_day("2026-03-05", source)
    assert not job.source_has_day("2026-01-01", source)
    assert not job.source_has_day("2026-03-05", tmp_path / "missing.csv")  # まだ届いていない


def test_runner_respects_order():
    seen = []
    tasks = {n: (lambda n=n: seen.append(n)) for n in "abcd"}
    deps = {"b": {"a"}, "c": {"a"}, "d": {"b", "c"}}
    assert set(runner.run(tasks, deps).values()) == {"success"}
    assert seen[0] == "a" and seen[-1] == "d"


def test_runner_skips_downstream_but_runs_other_branches():
    def broken():
        raise RuntimeError("x")

    ran = []
    tasks = {"a": lambda: None, "b": broken, "c": lambda: ran.append("c"), "d": lambda: ran.append("d")}
    deps = {"b": {"a"}, "c": {"a"}, "d": {"b", "c"}}
    state = runner.run(tasks, deps)
    assert state == {"a": "success", "b": "failed", "c": "success", "d": "upstream_failed"}
    assert ran == ["c"]  # b の失敗でも、関係のない c は動き、d は動かない


def test_runner_rejects_cycles():
    with pytest.raises(CycleError):
        runner.run({"a": lambda: None, "b": lambda: None}, {"a": {"b"}, "b": {"a"}})


DAG_FILE = HERE / "neboske_daily_sales.py"


def test_dag_file_is_valid_python_with_the_settings_in_the_book():
    tree = ast.parse(DAG_FILE.read_text(encoding="utf-8"))
    compile(tree, str(DAG_FILE), "exec")
    text = DAG_FILE.read_text(encoding="utf-8")
    for needle in ('schedule="@daily"', "catchup=False", '"retries": 2', "max_active_runs=1"):
        assert needle in text
    imports = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports <= {"logging", "os", "sys", "datetime", "pathlib", "daily_job", "airflow"}


def test_dag_tasks_call_the_job(source, tmp_path, monkeypatch):
    """DAG ファイルを、データ基盤の部分だけ素通しにしたスタブで読み込み、タスクの中身を直接呼びます。"""
    # CI の DagBag は、ある 2 つの語を両方含む .py を DAG の候補として読み込む。
    # このテストファイルが候補にならないよう、パッケージ名を 2 つに分けて書く。
    pkg = "air" + "flow"

    class Task:
        def __call__(self, fn):
            return fn

        def sensor(self, **kwargs):
            return lambda fn: fn

    decorators = types.ModuleType(pkg + ".decorators")
    decorators.task = Task()
    decorators.dag = lambda **kwargs: (lambda fn: (lambda: None))  # 本物は DAG を作る。ここでは何もしない
    monkeypatch.setitem(sys.modules, pkg, types.ModuleType(pkg))
    monkeypatch.setitem(sys.modules, pkg + ".decorators", decorators)
    monkeypatch.setenv("NEBOSKE_WORK", str(tmp_path))
    monkeypatch.syspath_prepend(str(HERE))
    out_source = tmp_path / "source" / "sales.csv"
    make_source.write_sales(out_source)

    mod = _load("neboske_daily_sales", DAG_FILE)
    assert mod.wait_for_source("2026-03-05") is True
    assert mod.wait_for_source("2026-01-01") is False
    assert mod.build("2026-03-05") == {"day": "2026-03-05", "rows": 5}
    assert (tmp_path / "out" / "daily_sales" / "date=2026-03-05.csv").exists()
    assert mod.build("2026-03-05") == {"day": "2026-03-05", "rows": 5}  # 再実行しても同じ
    mod.report({"day": "2026-03-05", "rows": 5})
