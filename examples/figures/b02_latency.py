"""第 2 章の図: 操作ごとの時間の桁（対数軸）。

data/tables/b02-latency.csv を読んで描きます。値の出典は第 2 章の参考文献を見てください。
"""
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# CSV の日本語の操作名を、図に使う英語のラベルに対応させます（図のフォントに日本語が無いため）。
LABELS = {
    "L1 キャッシュの参照": "L1 cache reference",
    "分岐予測のはずれ": "Branch mispredict",
    "L2 キャッシュの参照": "L2 cache reference",
    "ミューテックスのロックと解除": "Mutex lock/unlock",
    "メインメモリの参照": "Main memory reference",
    "1 KB を Zippy で圧縮": "Compress 1 KB (Zippy)",
    "1 Gbps のネットワークで 1 KB を送る": "Send 1 KB over 1 Gbps",
    "SSD から 4 KB をランダムに読む": "Random read 4 KB, SSD",
    "メモリから 1 MB を順に読む": "Sequential read 1 MB, memory",
    "同じデータセンター内の往復": "Round trip, same datacenter",
    "SSD から 1 MB を順に読む": "Sequential read 1 MB, SSD",
    "ディスクのシーク": "Disk seek",
    "ディスクから 1 MB を順に読む": "Sequential read 1 MB, disk",
    "カリフォルニア → オランダ → カリフォルニアのパケット": "Packet CA -> Netherlands -> CA",
}


def main() -> None:
    with open(ROOT / "data" / "tables" / "b02-latency.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    names = [LABELS[r["操作"]] for r in rows]
    values = [float(r["時間(ナノ秒)"]) for r in rows]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(names, values, color="#81A1C1")
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.set_xlabel("Time (ns, log scale; each gridline is 10x)")
    ax.bar_label(bars, labels=[f"{v:g} ns" for v in values], padding=3, fontsize=8)
    ax.set_xlim(0.1, max(values) * 30)
    ax.grid(axis="x", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Latency numbers (about 2012 figures; orders of magnitude only)", fontsize=11)
    fig.tight_layout()

    out = ROOT / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "b02_latency.svg", format="svg")


if __name__ == "__main__":
    main()
