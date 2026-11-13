"""ビルド前に examples/figures/*.py をすべて実行して図（SVG）を作る MkDocs hook。

各スクリプトは book/assets/figures/ に SVG を書きます（そこは git に入れません）。
run_figures は MkDocs に依存しません。
"""
import subprocess
import sys
from pathlib import Path


def run_figures(root: Path) -> list[Path]:
    """root/examples/figures/*.py を名前順に実行し、実行したスクリプトを返します。失敗したら例外にします。"""
    out = root / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    scripts = sorted((root / "examples" / "figures").glob("*.py"))
    for script in scripts:
        subprocess.run([sys.executable, str(script)], cwd=root, check=True)
    return scripts


def on_pre_build(config):
    run_figures(Path(config["config_file_path"]).parent)
