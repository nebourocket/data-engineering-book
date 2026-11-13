"""第 2 章の図: 操作ごとの時間の桁（対数軸）。

data/tables/b02-latency.csv を読んで描きます。値の出典は第 2 章の参考文献を見てください。
"""
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from _style import use_japanese_font  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    use_japanese_font()
    with open(ROOT / "data" / "tables" / "b02-latency.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    names = [r["操作"] for r in rows]
    values = [float(r["時間(ナノ秒)"]) for r in rows]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.barh(names, values, color="#81A1C1")
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.set_xlabel("時間（ナノ秒、対数軸。目盛りが 1 つ進むと 10 倍）")
    ax.bar_label(bars, labels=[f"{v:g} ns" for v in values], padding=3, fontsize=8)
    ax.set_xlim(0.1, max(values) * 30)
    ax.grid(axis="x", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("操作ごとの時間の桁（2012 年ごろの値。桁の目安）", fontsize=11)
    fig.tight_layout()

    out = ROOT / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "b02_latency.svg", format="svg")


if __name__ == "__main__":
    main()
