"""第 6 章の図: GROUP BY customer_id を、カードを山に分ける作業として描く。

examples/s06/setup.sql の orders を、そのまま描きます（山の枚数と合計は SQL の集計結果です）。
"""
import sys
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "examples" / "figures"))
from _style import use_japanese_font  # noqa: E402

COLORS = {1: "#88C0D0", 2: "#A3BE8C", 3: "#EBCB8B"}


def card(ax, x, y, order_id, amount, color):
    ax.add_patch(FancyBboxPatch((x, y), 1.5, 0.9, boxstyle="round,pad=0.02,rounding_size=0.1",
                                facecolor=color, edgecolor="#4C566A"))
    ax.text(x + 0.75, y + 0.45, f"注文 {order_id}\n{amount:,} 円", ha="center", va="center", fontsize=9)


def main() -> None:
    use_japanese_font()
    con = duckdb.connect()
    con.execute((ROOT / "examples" / "s06" / "setup.sql").read_text(encoding="utf-8"))
    orders = con.execute("SELECT order_id, customer_id, amount FROM orders ORDER BY order_id").fetchall()
    piles = con.execute(
        "SELECT customer_id, count(*), sum(amount) FROM orders GROUP BY customer_id ORDER BY customer_id"
    ).fetchall()

    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.4)
    ax.axis("off")

    ax.text(0.1, 6.05, "1. 注文のカード 6 枚 (今の並び順)", fontsize=11, fontweight="bold")
    for i, (order_id, customer_id, amount) in enumerate(orders):
        card(ax, 0.1 + i * 1.65, 5.0, order_id, amount, COLORS[customer_id])

    ax.text(0.1, 4.45, "2. customer_id が同じカードを 1 つの山に集める (GROUP BY customer_id)", fontsize=11,
            fontweight="bold")
    for p, (customer_id, count, total) in enumerate(piles):
        x = 0.4 + p * 3.3
        mine = [o for o in orders if o[1] == customer_id]
        for k, (order_id, _, amount) in enumerate(mine):
            card(ax, x + k * 0.15, 3.0 - k * 0.95, order_id, amount, COLORS[customer_id])
        ax.text(x, 0.75, f"customer_id = {customer_id}", fontsize=10, fontweight="bold")
        ax.text(x, 0.2, f"count(*) = {count}   sum(amount) = {total:,}", fontsize=10)

    ax.text(0.1, -0.35, "3. 山ごとに 1 行の結果になる (3 行)", fontsize=11, fontweight="bold")
    fig.tight_layout()

    out = ROOT / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "s06_group_by.svg", format="svg")


if __name__ == "__main__":
    main()
