"""図の共通設定（日本語フォント）。

図のスクリプトから `from _style import use_japanese_font` で読み込みます。
hooks/figures.py は `python examples/figures/名前.py` で実行するので、
スクリプトのフォルダ（examples/figures/）が import パスに入ります。
"""
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 候補のうち、手元に入っているものだけを使います（無いものを並べると警告が大量に出るため）。
_CANDIDATES = ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic"]


def use_japanese_font() -> None:
    """日本語が描けるフォントを既定にします。Noto（fonts-noto-cjk）が無ければ次の候補を使います。"""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = [name for name in _CANDIDATES if name in installed] + ["DejaVu Sans"]
    # 負の数のマイナス記号に、Unicode の「−」ではなく ASCII の「-」を使います。
    plt.rcParams["axes.unicode_minus"] = False
