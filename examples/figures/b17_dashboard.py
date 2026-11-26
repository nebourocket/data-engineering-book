"""第 17 章の図: 日次売上と品質のダッシュボード。

examples/b17/pipeline.py の run() を、手元のフォルダに置く形 (S3_ENDPOINT なし) で動かし、できた図を
book/assets/figures/ (en・zh は book/assets/figures/<lang>/) にコピーします。図の中の文字は、
examples/b17/dashboard.py が FIGURE_LANG を見て言語ごとに変えます。
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

from _style import figure_dir, figure_lang

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from examples.b17.pipeline import make_client, run  # noqa: E402


def main() -> None:
    lang = figure_lang()
    os.environ.pop("S3_ENDPOINT", None)  # 図のビルドはサービスなしで動かす (手元のフォルダに置く)
    with tempfile.TemporaryDirectory() as work:
        figure = run(make_client(work, "neboske-lake"), "neboske-lake", "2026-07-01", work)
        shutil.copy(figure, figure_dir(ROOT, lang) / "b17_dashboard.svg")


if __name__ == "__main__":
    main()
