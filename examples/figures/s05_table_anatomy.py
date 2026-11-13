"""第 5 章の図: 表の列・行・セル・主キーが、どこを指すか。

examples/s05/create_products.sql で作った products の先頭 4 行を、そのまま描きます。
"""
import sys
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "examples" / "figures"))
from _style import use_japanese_font  # noqa: E402

WIDTHS = [1.4, 2.6, 1.8, 1.4, 1.2]


def main() -> None:
    use_japanese_font()
    con = duckdb.connect()
    con.execute((ROOT / "examples" / "s05" / "create_products.sql").read_text(encoding="utf-8"))
    cursor = con.execute("SELECT * FROM products ORDER BY product_id LIMIT 4")
    header = [c[0] for c in cursor.description]
    rows = [[str(v) for v in r] for r in cursor.fetchall()]

    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.set_xlim(-0.2, sum(WIDTHS) + 2.2)
    ax.set_ylim(-1.9, 5.1)
    ax.axis("off")
    xs = [sum(WIDTHS[:i]) for i in range(len(WIDTHS))]

    def cell(col, row, text, face, weight="normal"):
        """row = 0 が見出し、1 以降がデータの行。"""
        y = 4 - row
        ax.add_patch(Rectangle((xs[col], y), WIDTHS[col], 1, facecolor=face, edgecolor="#4C566A"))
        ax.text(xs[col] + WIDTHS[col] / 2, y + 0.5, text, ha="center", va="center", fontsize=11, fontweight=weight)

    for c, name in enumerate(header):
        cell(c, 0, name, "#D8DEE9", "bold")
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            face = "#FFFFFF"
            if c == 3:
                face = "#E5F0F5"      # 列 (price)
            if r == 3:
                face = "#E4EFDB"      # 行 (3 行目)
            if c == 3 and r == 3:
                face = "#F5E6B8"      # セル
            cell(c, r, value, face)

    # 主キーの列を赤い枠で囲む
    ax.add_patch(Rectangle((xs[0], 0), WIDTHS[0], 5, fill=False, edgecolor="#BF616A", linewidth=2.5))
    ax.annotate("主キー\n(行を 1 つに決める列)", xy=(xs[0] + 0.7, 0), xytext=(0.2, -1.4),
                ha="left", color="#BF616A", fontsize=10, arrowprops={"arrowstyle": "->", "color": "#BF616A"})
    ax.annotate("列 (column)\n同じ種類の値が縦に並ぶ", xy=(xs[3] + 0.6, 0), xytext=(xs[3] - 1.2, -1.4),
                ha="left", color="#5E81AC", fontsize=10, arrowprops={"arrowstyle": "->", "color": "#5E81AC"})
    ax.annotate("行 (row)\n1 件分のまとまり", xy=(sum(WIDTHS), 1.5), xytext=(sum(WIDTHS) + 0.2, 1.3),
                ha="left", color="#6B8E4E", fontsize=10, arrowprops={"arrowstyle": "->", "color": "#6B8E4E"})
    ax.annotate("セル\n(行と列の交点)", xy=(xs[3] + 0.7, 1.7), xytext=(xs[3] - 0.3, 5.0),
                ha="left", color="#B48E32", fontsize=10, arrowprops={"arrowstyle": "->", "color": "#B48E32"})
    ax.set_title("表の名前: products", fontsize=12, loc="left")
    fig.tight_layout()

    out = ROOT / "book" / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "s05_table_anatomy.svg", format="svg")


if __name__ == "__main__":
    main()
