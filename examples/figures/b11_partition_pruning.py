"""第 11 章の図: パーティションの条件の有無で、開いたファイル数と読んだバイト数がどう変わるか。

examples/b11/partition_demo.py の測定結果をそのまま描きます（バイト数は実行環境で少し変わります）。
"""
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "examples" / "b11"))
from _style import figure_dir, figure_lang, labels, use_font  # noqa: E402
from partition_demo import run_scenarios, sales_lines, write_partitioned  # noqa: E402

# 言語別のラベル（figure_lang 対応）。
LABELS = {
    "ja": {
        "full_scan": "条件なし\n(全月・2 列)",
        "month_filter": "month = '2026-03'\n(2 列)",
        "date_filter_only": "ordered_at だけ\n(2 列)",
        "select_star": "month = '2026-03'\n+ SELECT *",
        "files": "開いたファイルの数（全 6 ファイル）",
        "bytes": "読んだバイト数（kB）",
        "suptitle": "月ごとに分けた売上明細（約 15 万行）に、4 通りのクエリを流したとき",
    },
    "en": {
        "full_scan": "No condition\n(all months, 2 columns)",
        "month_filter": "month = '2026-03'\n(2 columns)",
        "date_filter_only": "ordered_at only\n(2 columns)",
        "select_star": "month = '2026-03'\n+ SELECT *",
        "files": "Files opened (6 files in total)",
        "bytes": "Bytes read (kB)",
        "suptitle": "Four queries run on sales lines split by month (about 150,000 rows)",
    },
    "zh": {
        "full_scan": "无条件\n(所有月份，2 列)",
        "month_filter": "month = '2026-03'\n(2 列)",
        "date_filter_only": "仅 ordered_at\n(2 列)",
        "select_star": "month = '2026-03'\n+ SELECT *",
        "files": "打开的文件数（共 6 个文件）",
        "bytes": "读取的字节数（kB）",
        "suptitle": "对按月拆分的销售明细（约 15 万行）运行 4 种查询时",
    },
}
COLORS = ["#81A1C1", "#A3BE8C", "#EBCB8B", "#BF616A"]


def main() -> None:
    lang = figure_lang()
    text = labels(LABELS, lang)
    use_font(lang)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "sales"
        write_partitioned(root, sales_lines())
        results = run_scenarios(root)
    names = [text[r["name"]] for r in results]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    panels = [("files_read", text["files"], 1),
              ("bytes_read", text["bytes"], 1000)]
    for ax, (key, title, div) in zip(axes, panels):
        values = [r[key] / div for r in results]
        bars = ax.bar(names, values, color=COLORS)
        ax.set_title(title, fontsize=11)
        ax.bar_label(bars, labels=[f"{v:,.0f}" for v in values], padding=3, fontsize=9)
        ax.set_ylim(0, max(values) * 1.18)
        ax.tick_params(axis="x", labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(text["suptitle"], fontsize=12)
    fig.tight_layout()

    fig.savefig(figure_dir(ROOT, lang) / "b11_partition_pruning.svg", format="svg")


if __name__ == "__main__":
    main()
