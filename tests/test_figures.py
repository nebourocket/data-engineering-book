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
