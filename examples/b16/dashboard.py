"""日次売上と品質のダッシュボードを 1 枚の図 (SVG) にします。"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "figures"))
from _style import use_japanese_font  # noqa: E402

COLORS = {"合格": "#A3BE8C", "警告": "#EBCB8B", "不合格": "#BF616A"}


def draw(con, run_dt, out_path):
    """analytics.fct_daily_sales と dq_results を読んで、out_path に SVG を書きます。"""
    use_japanese_font()
    sales = con.execute("""
        SELECT order_date, sales FROM analytics.fct_daily_sales ORDER BY order_date""").fetchall()
    checks = con.execute("""
        SELECT check_name, severity, passed FROM dq_results WHERE run_dt = ? ORDER BY rowid""", [run_dt]).fetchall()
    days = [d for d, _ in sales]
    values = [v for _, v in sales]
    average = [sum(values[max(0, i - 6):i + 1]) / len(values[max(0, i - 6):i + 1]) for i in range(len(values))]

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7), height_ratios=[3, 2])
    top.bar(days, values, color="#88C0D0", width=1.0, label="日別売上")
    top.plot(days, average, color="#5E81AC", linewidth=2, label="7 日移動平均")
    top.set_title(f"ねぼすけ商店 日次売上 (取り込み日 {run_dt}、キャンセル除く)", fontsize=12)
    top.set_ylabel("売上 (円)")
    top.legend(loc="upper left")
    top.spines[["top", "right"]].set_visible(False)

    bottom.set_xlim(0, 1)
    bottom.set_ylim(0, len(checks))
    bottom.axis("off")
    bottom.set_title("品質チェックの結果", fontsize=12)
    for row, (name, severity, passed) in enumerate(checks):
        label = "合格" if passed else ("警告" if severity == "warn" else "不合格")
        y = len(checks) - row - 0.5
        bottom.text(0.02, y, f"[{label}]", color=COLORS[label], fontsize=11, va="center", fontweight="bold")
        bottom.text(0.14, y, f"{name} ({severity})", fontsize=10, va="center")
    fig.tight_layout()
    fig.savefig(out_path, format="svg")
    plt.close(fig)
