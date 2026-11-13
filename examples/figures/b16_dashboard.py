"""第 16 章の図: 日次売上と品質のダッシュボード。

examples/b16/pipeline.py の run() を、手元のフォルダに置く形 (DirStore) で動かし、できた図を book/assets/figures/ にコピーします。
"""
import shutil
import sys
import tempfile
from pathlib import Path

from _style import use_japanese_font

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from examples.b16.pipeline import run  # noqa: E402
from examples.b16.store import DirStore  # noqa: E402


def main() -> None:
    use_japanese_font()
    with tempfile.TemporaryDirectory() as work:
        figure = run(DirStore(Path(work) / "landing"), "2026-07-01", work)
        out = ROOT / "book" / "assets" / "figures"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy(figure, out / "b16_dashboard.svg")


if __name__ == "__main__":
    main()
