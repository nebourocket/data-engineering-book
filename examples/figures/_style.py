"""図の共通設定（日本語フォント）。

図のスクリプトから `from _style import use_japanese_font` で読み込みます。
hooks/figures.py は `python examples/figures/名前.py` で実行するので、
スクリプトのフォルダ（examples/figures/）が import パスに入ります。
"""
import os
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager

# 候補のうち、手元に入っているものだけを使います（無いものを並べると警告が大量に出るため）。
_CANDIDATES = ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic"]


def figure_lang() -> str:
    """作る図の言語（ja / en / zh）。hooks/figures.py が環境変数 FIGURE_LANG で渡します。単独実行では ja です。"""
    return os.environ.get("FIGURE_LANG", "ja")


def labels(by_lang: dict, lang: str | None = None) -> dict:
    """言語ごとのラベルの辞書 {"ja": {...}, "en": {...}, ...} から、その言語の分を返します。無い言語は ja です。"""
    lang = lang or figure_lang()
    return by_lang.get(lang, by_lang["ja"])


def figure_dir(root: Path, lang: str | None = None) -> Path:
    """図を書き出すフォルダ。ja は book/assets/figures/、ほかは book/assets/figures/<lang>/ です。"""
    lang = lang or figure_lang()
    out = Path(root) / "book" / "assets" / "figures"
    if lang != "ja":
        out = out / lang
    out.mkdir(parents=True, exist_ok=True)
    return out


def use_font(lang: str | None = None) -> None:
    """言語に合うフォントを既定にします。中国語は簡体字の Noto Sans CJK SC を先に探します。"""
    lang = lang or figure_lang()
    order = ["Noto Sans CJK SC"] + _CANDIDATES if lang == "zh" else _CANDIDATES + ["Noto Sans CJK SC"]
    installed = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = [name for name in order if name in installed] + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def use_japanese_font() -> None:
    """日本語が描けるフォントを既定にします。Noto（fonts-noto-cjk）が無ければ次の候補を使います。"""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = [name for name in _CANDIDATES if name in installed] + ["DejaVu Sans"]
    # 負の数のマイナス記号に、Unicode の「−」ではなく ASCII の「-」を使います。
    plt.rcParams["axes.unicode_minus"] = False
