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
from _style import use_japanese_font  # noqa: E402
from file_formats import measure  # noqa: E402

COLORS = {"CSV": "#81A1C1", "CSV (gzip)": "#88C0D0", "JSON Lines": "#BF616A",
          "Parquet (snappy)": "#A3BE8C", "Parquet (zstd)": "#8FBCBB"}


def main() -> None:
    use_japanese_font()
    results = measure()
    names = [r["format"] for r in results]
    colors = [COLORS[n] for n in names]
    rows = results[0]["rows"]

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    panels = [("size_mb", "ファイルサイズ（MB）"), ("load_all_s", "全列を読み込む時間（秒）"),
              ("sum_one_col_s", "1 列の合計を取る時間（秒）")]
    for ax, (key, title) in zip(axes, panels):
        values = [r[key] for r in results]
        bars = ax.barh(names, values, color=colors)
        ax.set_title(title, fontsize=11)
        ax.invert_yaxis()
        ax.bar_label(bars, labels=[f"{v:.3g}" for v in values], padding=3, fontsize=9)
        ax.set_xlim(0, max(values) * 1.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"同じ売上明細（{rows:,} 行）を 5 通りの形式で保存したとき", fontsize=12)
    fig.tight_layout()

    out = ROOT / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "b02_formats.svg", format="svg")


if __name__ == "__main__":
    main()
