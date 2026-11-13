"""第 6 章の図: customers と orders を customer_id でつなぐ線。

examples/s06/setup.sql の中身をそのまま描きます。線が 1 本も出ない顧客が、INNER JOIN で消える行です。
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

COLORS = {1: "#88C0D0", 2: "#A3BE8C", 3: "#EBCB8B", 4: "#D8DEE9"}


def box(ax, x, y, text, color, width=3.4):
    ax.add_patch(FancyBboxPatch((x, y), width, 0.7, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor=color, edgecolor="#4C566A"))
    ax.text(x + width / 2, y + 0.35, text, ha="center", va="center", fontsize=10)


def main() -> None:
    use_japanese_font()
    con = duckdb.connect()
    con.execute((ROOT / "examples" / "s06" / "setup.sql").read_text(encoding="utf-8"))
    customers = con.execute("SELECT customer_id, name FROM customers ORDER BY customer_id").fetchall()
    orders = con.execute("SELECT order_id, customer_id, amount FROM orders ORDER BY order_id").fetchall()

    fig, ax = plt.subplots(figsize=(9, 5.4))
    ax.set_xlim(0, 9)
    ax.set_ylim(-0.4, 6.6)
    ax.axis("off")
    ax.text(0.1, 6.25, "customers (左の表)", fontsize=11, fontweight="bold")
    ax.text(5.5, 6.25, "orders (右の表)", fontsize=11, fontweight="bold")

    left_y = {}
    for i, (customer_id, name) in enumerate(customers):
        y = 5.2 - i * 1.5
        left_y[customer_id] = y + 0.35
        box(ax, 0.1, y, f"{customer_id}  {name}", COLORS[customer_id])
    matched = set()
    for i, (order_id, customer_id, amount) in enumerate(orders):
        y = 5.4 - i * 1.05
        box(ax, 5.5, y, f"注文 {order_id} (customer_id = {customer_id}, {amount:,} 円)", COLORS[customer_id], 3.4)
        ax.plot([3.5, 5.5], [left_y[customer_id], y + 0.35], color="#4C566A", linewidth=1.2)
        matched.add(customer_id)
    for customer_id, _ in customers:
        if customer_id not in matched:
            ax.text(3.7, left_y[customer_id], "つながる注文がない", color="#BF616A", fontsize=10, va="center")
    fig.tight_layout()

    out = ROOT / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "s06_join.svg", format="svg")


if __name__ == "__main__":
    main()
