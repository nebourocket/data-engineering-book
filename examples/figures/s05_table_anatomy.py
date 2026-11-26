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
from _style import figure_dir, figure_lang, labels, use_font  # noqa: E402

WIDTHS = [1.4, 2.6, 1.8, 1.4, 1.2]

# 言語別のラベル（figure_lang 対応）。ja の図は book/assets/figures/、en・zh は <lang>/ に出ます。
LABELS = {
    "ja": {"pk": "主キー\n(行を 1 つに決める列)", "col": "列 (column)\n同じ種類の値が縦に並ぶ",
           "row": "行 (row)\n1 件分のまとまり", "cell": "セル\n(行と列の交点)", "title": "表の名前: products"},
    "en": {"pk": "Primary key\n(the column that picks one row)", "col": "Column\nValues of the same kind run down",
           "row": "Row\nOne record", "cell": "Cell\n(where a row and a column meet)", "title": "Table name: products"},
    "zh": {"pk": "主键\n（能唯一确定一行的列）", "col": "列（column）\n同一类的值纵向排列",
           "row": "行（row）\n一条记录", "cell": "单元格\n（行和列的交叉点）", "title": "表名：products"},
}


# 図に出すデータの値の訳（図は挿絵なので、データの値も図の言語にします。日本語はそのまま）。
VALUES = {
    "en": {"枕": "pillow", "毛布": "blanket", "アイマスク": "eye mask", "光る目覚まし": "light-up alarm clock",
           "寝具": "bedding", "目覚まし": "alarm clocks"},
    "zh": {"枕": "枕头", "毛布": "毛毯", "アイマスク": "眼罩", "光る目覚まし": "发光闹钟",
           "寝具": "床上用品", "目覚まし": "闹钟"},
}


def main() -> None:
    lang = figure_lang()
    text = labels(LABELS, lang)
    use_font(lang)
    con = duckdb.connect()
    con.execute((ROOT / "examples" / "s05" / "create_products.sql").read_text(encoding="utf-8"))
    cursor = con.execute("SELECT * FROM products ORDER BY product_id LIMIT 4")
    header = [c[0] for c in cursor.description]
    rows = [[VALUES.get(lang, {}).get(str(v), str(v)) for v in r] for r in cursor.fetchall()]

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
    ax.annotate(text["pk"], xy=(xs[0] + 0.7, 0), xytext=(0.2, -1.4),
                ha="left", color="#BF616A", fontsize=10, arrowprops={"arrowstyle": "->", "color": "#BF616A"})
    ax.annotate(text["col"], xy=(xs[3] + 0.6, 0), xytext=(xs[3] - 1.2, -1.4),
                ha="left", color="#5E81AC", fontsize=10, arrowprops={"arrowstyle": "->", "color": "#5E81AC"})
    ax.annotate(text["row"], xy=(sum(WIDTHS), 1.5), xytext=(sum(WIDTHS) + 0.2, 1.3),
                ha="left", color="#6B8E4E", fontsize=10, arrowprops={"arrowstyle": "->", "color": "#6B8E4E"})
    ax.annotate(text["cell"], xy=(xs[3] + 0.7, 1.7), xytext=(xs[3] - 0.3, 5.0),
                ha="left", color="#B48E32", fontsize=10, arrowprops={"arrowstyle": "->", "color": "#B48E32"})
    ax.set_title(text["title"], fontsize=12, loc="left")
    fig.tight_layout()

    fig.savefig(figure_dir(ROOT, lang) / "s05_table_anatomy.svg", format="svg")


if __name__ == "__main__":
    main()
