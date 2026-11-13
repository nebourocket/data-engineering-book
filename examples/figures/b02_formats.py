"""第 2 章の図: CSV / JSON Lines / Parquet のファイルサイズと読み込み時間。

examples/b02/formats.py の計測結果をそのまま描きます。数値は実行のたびに変わります。
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "examples" / "b02"))
from file_formats import measure  # noqa: E402

COLORS = {"CSV": "#81A1C1", "CSV (gzip)": "#88C0D0", "JSON Lines": "#BF616A",
          "Parquet (snappy)": "#A3BE8C", "Parquet (zstd)": "#8FBCBB"}


def main() -> None:
    results = measure()
    names = [r["format"] for r in results]
    colors = [COLORS[n] for n in names]
    rows = results[0]["rows"]

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    panels = [("size_mb", "File size (MB)"), ("load_all_s", "Load all columns (s)"),
              ("sum_one_col_s", "Sum of one column (s)")]
    for ax, (key, title) in zip(axes, panels):
        values = [r[key] for r in results]
        bars = ax.barh(names, values, color=colors)
        ax.set_title(title, fontsize=11)
        ax.invert_yaxis()
        ax.bar_label(bars, labels=[f"{v:.3g}" for v in values], padding=3, fontsize=9)
        ax.set_xlim(0, max(values) * 1.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Same sales lines ({rows:,} rows), five ways to store them", fontsize=12)
    fig.tight_layout()

    out = ROOT / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "b02_formats.svg", format="svg")


if __name__ == "__main__":
    main()
