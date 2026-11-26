"""第 2 章の図: CSV / JSON Lines / Parquet のファイルサイズと読み込み時間。

examples/b02/file_formats.py の計測結果をそのまま描きます。数値は実行のたびに変わります。
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "examples" / "b02"))
from _style import figure_dir, figure_lang, labels, use_font  # noqa: E402
from file_formats import measure  # noqa: E402

COLORS = {"CSV": "#81A1C1", "CSV (gzip)": "#88C0D0", "JSON Lines": "#BF616A",
          "Parquet (snappy)": "#A3BE8C", "Parquet (zstd)": "#8FBCBB"}


# 言語別のラベル（figure_lang 対応）。ja の図は book/assets/figures/、en・zh は <lang>/ に出ます。
LABELS = {
    "ja": {"panels": ["ファイルサイズ（MB）", "全列を読み込む時間（秒）", "1 列の合計を取る時間（秒）"],
           "title": "同じ売上明細（{rows:,} 行）を 5 通りの形式で保存したとき"},
    "en": {"panels": ["File size (MB)", "Time to read all columns (s)", "Time to sum one column (s)"],
           "title": "The same sales lines ({rows:,} rows) saved in 5 formats"},
    "zh": {"panels": ["文件大小（MB）", "读取全部列的时间（秒）", "对一列求和的时间（秒）"],
           "title": "同一份销售明细（{rows:,} 行）以 5 种格式保存时"},
}


def main() -> None:
    lang = figure_lang()
    text = labels(LABELS, lang)
    use_font(lang)
    results = measure()
    names = [r["format"] for r in results]
    colors = [COLORS[n] for n in names]
    rows = results[0]["rows"]

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    panels = list(zip(["size_mb", "load_all_s", "sum_one_col_s"], text["panels"]))
    for ax, (key, title) in zip(axes, panels):
        values = [r[key] for r in results]
        bars = ax.barh(names, values, color=colors)
        ax.set_title(title, fontsize=11)
        ax.invert_yaxis()
        ax.bar_label(bars, labels=[f"{v:.3g}" for v in values], padding=3, fontsize=9)
        ax.set_xlim(0, max(values) * 1.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(text["title"].format(rows=rows), fontsize=12)
    fig.tight_layout()

    fig.savefig(figure_dir(ROOT, lang) / "b02_formats.svg", format="svg")


if __name__ == "__main__":
    main()
