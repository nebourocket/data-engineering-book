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
from _style import figure_dir, figure_lang, labels, use_font  # noqa: E402

COLORS = {1: "#88C0D0", 2: "#A3BE8C", 3: "#EBCB8B", 4: "#D8DEE9"}

# 言語別のラベル（figure_lang 対応）。ja の図は book/assets/figures/、en・zh は <lang>/ に出ます。
# names は customers.name（日本語のデータ値）を図の言語に置き換える表です。
LABELS = {
    "ja": {"left": "customers (左の表)", "right": "orders (右の表)",
           "order": "注文 {order_id} (customer_id = {customer_id}, {amount:,} 円)",
           "nomatch": "つながる注文がない", "names": {}},
    "en": {"left": "customers (left table)", "right": "orders (right table)",
           "order": "Order {order_id} (customer_id = {customer_id}, {amount:,} yen)",
           "nomatch": "No matching order",
           "names": {"佐藤 太郎": "Taro Sato", "鈴木 花子": "Hanako Suzuki", "高橋 健": "Ken Takahashi",
                     "田中 美咲": "Misaki Tanaka"}},
    "zh": {"left": "customers（左表）", "right": "orders（右表）",
           "order": "订单 {order_id}（customer_id = {customer_id}，{amount:,} 日元）",
           "nomatch": "没有可连接的订单",
           "names": {"佐藤 太郎": "佐藤太郎", "鈴木 花子": "铃木花子", "高橋 健": "高桥健",
                     "田中 美咲": "田中美咲"}},
}


def box(ax, x, y, text, color, width=3.4):
    ax.add_patch(FancyBboxPatch((x, y), width, 0.7, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor=color, edgecolor="#4C566A"))
    ax.text(x + width / 2, y + 0.35, text, ha="center", va="center", fontsize=10)


def main() -> None:
    lang = figure_lang()
    text = labels(LABELS, lang)
    use_font(lang)
    con = duckdb.connect()
    con.execute((ROOT / "examples" / "s06" / "setup.sql").read_text(encoding="utf-8"))
    customers = con.execute("SELECT customer_id, name FROM customers ORDER BY customer_id").fetchall()
    orders = con.execute("SELECT order_id, customer_id, amount FROM orders ORDER BY order_id").fetchall()

    fig, ax = plt.subplots(figsize=(9, 5.4))
    ax.set_xlim(0, 9)
    ax.set_ylim(-0.4, 6.6)
    ax.axis("off")
    ax.text(0.1, 6.25, text["left"], fontsize=11, fontweight="bold")
    ax.text(5.5, 6.25, text["right"], fontsize=11, fontweight="bold")

    left_y = {}
    for i, (customer_id, name) in enumerate(customers):
        y = 5.2 - i * 1.5
        left_y[customer_id] = y + 0.35
        box(ax, 0.1, y, f"{customer_id}  {text['names'].get(name, name)}", COLORS[customer_id])
    matched = set()
    for i, (order_id, customer_id, amount) in enumerate(orders):
        y = 5.4 - i * 1.05
        box(ax, 5.5, y, text["order"].format(order_id=order_id, customer_id=customer_id, amount=amount), COLORS[customer_id], 3.4)
        ax.plot([3.5, 5.5], [left_y[customer_id], y + 0.35], color="#4C566A", linewidth=1.2)
        matched.add(customer_id)
    for customer_id, _ in customers:
        if customer_id not in matched:
            ax.text(3.7, left_y[customer_id], text["nomatch"], color="#BF616A", fontsize=10, va="center")
    fig.tight_layout()

    out = figure_dir(ROOT, lang)
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "s06_join.svg", format="svg")


if __name__ == "__main__":
    main()
