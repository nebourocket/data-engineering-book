"""第 2 章の図: 操作ごとの時間の桁（対数軸）。

data/tables/b02-latency.csv を読んで描きます。値の出典は第 2 章の参考文献を見てください。
"""
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from _style import figure_dir, figure_lang, labels, use_font  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# 言語別のラベル（figure_lang 対応）。操作名は data/tables/<lang>/b02-latency.csv の 1 列目を使います。
LABELS = {
    "ja": {"xlabel": "時間（ナノ秒、対数軸。目盛りが 1 つ進むと 10 倍）",
           "title": "操作ごとの時間の桁（2012 年ごろの値。桁の目安）"},
    "en": {"xlabel": "Time (nanoseconds, log axis. Each tick is 10 times the previous one)",
           "title": "Orders of magnitude of time per operation (values from around 2012, as a rough guide)"},
    "zh": {"xlabel": "时间（纳秒，对数轴。每前进一格为 10 倍）",
           "title": "各项操作耗时的数量级（2012 年前后的数值，仅作数量级参考）"},
}


def main() -> None:
    lang = figure_lang()
    text = labels(LABELS, lang)
    use_font(lang)
    # ja は data/tables/、en・zh は data/tables/<lang>/ の表を読みます（列の順は同じ: 操作・ナノ秒・引き延ばし）。
    table_dir = ROOT / "data" / "tables" / ("" if lang == "ja" else lang)
    with open(table_dir / "b02-latency.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))[1:]
    names = [r[0] for r in rows]
    values = [float(r[1]) for r in rows]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.barh(names, values, color="#81A1C1")
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.set_xlabel(text["xlabel"])
    ax.bar_label(bars, labels=[f"{v:g} ns" for v in values], padding=3, fontsize=8)
    ax.set_xlim(0.1, max(values) * 30)
    ax.grid(axis="x", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(text["title"], fontsize=11)
    fig.tight_layout()

    fig.savefig(figure_dir(ROOT, lang) / "b02_latency.svg", format="svg")


if __name__ == "__main__":
    main()
