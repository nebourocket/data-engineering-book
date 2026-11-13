"""図の共通設定（日本語フォント）。

図のスクリプトから `from _style import use_japanese_font` で読み込みます。
hooks/figures.py は `python examples/figures/名前.py` で実行するので、
スクリプトのフォルダ（examples/figures/）が import パスに入ります。
"""
import matplotlib.pyplot as plt


def use_japanese_font() -> None:
    """日本語が描けるフォントを既定にします。Noto（fonts-noto-cjk）が無ければ次の候補を使います。"""
    plt.rcParams["font.family"] = [
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "IPAexGothic",
        "DejaVu Sans",
    ]
    # 負の数のマイナス記号に、Unicode の「−」ではなく ASCII の「-」を使います。
    plt.rcParams["axes.unicode_minus"] = False
