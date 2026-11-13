import pytest
import subprocess

from hooks.figures import run_figures


def test_runs_every_script(tmp_path):
    figs = tmp_path / "examples" / "figures"
    figs.mkdir(parents=True)
    for name in ("a", "b"):
        (figs / f"{name}.py").write_text(
            "from pathlib import Path\n"
            f"Path('book/assets/figures/{name}.svg').write_text('<svg/>')\n")
    run_figures(tmp_path)
    assert (tmp_path / "book/assets/figures/a.svg").exists()
    assert (tmp_path / "book/assets/figures/b.svg").exists()


def test_no_scripts_is_fine(tmp_path):
    assert run_figures(tmp_path) == []


def test_failing_script_raises(tmp_path):
    figs = tmp_path / "examples" / "figures"
    figs.mkdir(parents=True)
    (figs / "bad.py").write_text("raise SystemExit(1)\n")
    with pytest.raises(subprocess.CalledProcessError):
        run_figures(tmp_path)


def test_skips_underscore_files(tmp_path):
    # _ で始まるファイルは共通部品なので実行しません（_style.py など）。
    figs = tmp_path / "examples" / "figures"
    figs.mkdir(parents=True)
    (figs / "_common.py").write_text("from pathlib import Path\nPath('ran.txt').write_text('x')\n")
    (figs / "a.py").write_text("from pathlib import Path\nPath('book/assets/figures/a.svg').write_text('<svg/>')\n")
    assert [p.name for p in run_figures(tmp_path)] == ["a.py"]
    assert not (tmp_path / "ran.txt").exists()


def test_script_can_import_underscore_module(tmp_path):
    # hook は python で直接スクリプトを実行するので、スクリプトのフォルダが import パスに入ります。
    figs = tmp_path / "examples" / "figures"
    figs.mkdir(parents=True)
    (figs / "_helper.py").write_text("VALUE = 'ok'\n")
    (figs / "a.py").write_text(
        "from pathlib import Path\n"
        "from _helper import VALUE\n"
        "Path('book/assets/figures/a.svg').write_text(VALUE)\n")
    run_figures(tmp_path)
    assert (tmp_path / "book/assets/figures/a.svg").read_text() == "ok"
