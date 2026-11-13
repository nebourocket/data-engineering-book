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
from _style import use_japanese_font  # noqa: E402
from partition_demo import run_scenarios, sales_lines, write_partitioned  # noqa: E402

LABELS = {
    "full_scan": "条件なし\n(全月・2 列)",
    "month_filter": "month = '2026-03'\n(2 列)",
    "date_filter_only": "ordered_at だけ\n(2 列)",
    "select_star": "month = '2026-03'\n+ SELECT *",
}
COLORS = ["#81A1C1", "#A3BE8C", "#EBCB8B", "#BF616A"]


def main() -> None:
    use_japanese_font()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "sales"
        write_partitioned(root, sales_lines())
        results = run_scenarios(root)
    labels = [LABELS[r["name"]] for r in results]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    panels = [("files_read", "開いたファイルの数（全 6 ファイル）", 1),
              ("bytes_read", "読んだバイト数（kB）", 1000)]
    for ax, (key, title, div) in zip(axes, panels):
        values = [r[key] / div for r in results]
        bars = ax.bar(labels, values, color=COLORS)
        ax.set_title(title, fontsize=11)
        ax.bar_label(bars, labels=[f"{v:,.0f}" for v in values], padding=3, fontsize=9)
        ax.set_ylim(0, max(values) * 1.18)
        ax.tick_params(axis="x", labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("月ごとに分けた売上明細（約 15 万行）に、4 通りのクエリを流したとき", fontsize=12)
    fig.tight_layout()

    out = ROOT / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "b11_partition_pruning.svg", format="svg")


if __name__ == "__main__":
    main()
