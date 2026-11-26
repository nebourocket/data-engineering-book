"""日次売上と品質のダッシュボードを 1 枚の図 (SVG) にします。"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "figures"))
from _style import figure_lang, labels, use_font  # noqa: E402

COLORS = {"pass": "#A3BE8C", "warn": "#EBCB8B", "fail": "#BF616A"}

# 言語別のラベル（第2章の b02_formats.py と同じ形）。図は挿絵なので、データの値も図の言語に訳します。
# names: 品質チェックの名前のうち、日本語で書かれているものの訳。
LABELS = {
    "ja": {"shop": "ねぼすけ商店", "sales": "日別売上", "average": "7 日移動平均",
           "title": "{shop} 日次売上 (取り込み日 {dt}、キャンセル除く)", "ylabel": "売上 (円)",
           "quality": "品質チェックの結果",
           "status": {"pass": "合格", "warn": "警告", "fail": "不合格"},
           "names": {}},
    "en": {"shop": "Neboske Shop", "sales": "Daily sales", "average": "7-day moving average",
           "title": "{shop} daily sales (ingest date {dt}, cancellations excluded)", "ylabel": "Sales (JPY)",
           "quality": "Quality check results",
           "status": {"pass": "PASS", "warn": "WARN", "fail": "FAIL"},
           "names": {"日別売上の合計が raw の明細と一致する":
                     "Daily sales total matches the raw line items"}},
    "zh": {"shop": "睡懒觉商店", "sales": "每日销售额", "average": "7 日移动平均",
           "title": "{shop} 每日销售额（导入日 {dt}，不含取消）", "ylabel": "销售额（日元）",
           "quality": "质量检查结果",
           "status": {"pass": "通过", "warn": "警告", "fail": "不通过"},
           "names": {"日別売上の合計が raw の明細と一致する":
                     "每日销售额合计与 raw 明细一致"}},
}


def draw(con, run_dt, out_path):
    """analytics.fct_daily_sales と dq_results を読んで、out_path に SVG を書きます。"""
    lang = figure_lang()
    text = labels(LABELS, lang)
    use_font(lang)
    sales = con.execute("""
        SELECT order_date, sales FROM analytics.fct_daily_sales ORDER BY order_date""").fetchall()
    checks = con.execute("""
        SELECT check_name, severity, passed FROM dq_results WHERE run_id = ? ORDER BY rowid""", [run_dt]).fetchall()
    days = [d for d, _ in sales]
    values = [v for _, v in sales]
    average = [sum(values[max(0, i - 6):i + 1]) / len(values[max(0, i - 6):i + 1]) for i in range(len(values))]

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7), height_ratios=[3, 2])
    top.bar(days, values, color="#88C0D0", width=1.0, label=text["sales"])
    top.plot(days, average, color="#5E81AC", linewidth=2, label=text["average"])
    top.set_title(text["title"].format(shop=text["shop"], dt=run_dt), fontsize=12)
    top.set_ylabel(text["ylabel"])
    top.legend(loc="upper left")
    top.spines[["top", "right"]].set_visible(False)

    bottom.set_xlim(0, 1)
    bottom.set_ylim(0, len(checks))
    bottom.axis("off")
    bottom.set_title(text["quality"], fontsize=12)
    for row, (name, severity, passed) in enumerate(checks):
        label = "pass" if passed else ("warn" if severity == "warn" else "fail")
        y = len(checks) - row - 0.5
        bottom.text(0.02, y, f"[{text['status'][label]}]", color=COLORS[label], fontsize=11,
                    va="center", fontweight="bold")
        bottom.text(0.14, y, f"{text['names'].get(name, name)} ({severity})", fontsize=10, va="center")
    fig.tight_layout()
    fig.savefig(out_path, format="svg")
    plt.close(fig)
