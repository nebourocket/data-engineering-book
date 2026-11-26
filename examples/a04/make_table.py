"""ウォーターマークの長さと、捨てた行・確定の遅れ・状態の大きさの表 (CSV) を作ります。"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import stream_sim  # noqa: E402

LATENESS = [0, 10, 30, 60, 120, 300, 600]
HEADER = ["遅延の分布", "ウォーターマーク(秒)", "捨てた行(%)", "誤った集計(%)", "誤差 中央値(%)", "誤差 p95(%)", "合計の取りこぼし(%)", "確定の遅れ 平均(秒)",
          "確定の遅れ p95(秒)", "状態の最大(件)"]


def tradeoff_rows():
    rows = []
    for model in stream_sim.MODELS:
        events = stream_sim.make_events(model)
        for lateness in LATENESS:
            r = stream_sim.evaluate(events, lateness)
            rows.append([model, lateness, f"{r['dropped_pct']:.2f}", f"{r['wrong_cells_pct']:.1f}",
                         f"{100 * r['rel_err_median']:.1f}", f"{100 * r['rel_err_p95']:.0f}",
                         f"{r['missing_total_pct']:.2f}", f"{r['delay_mean']:.0f}", r["delay_p95"], r["peak_state"]])
    return rows


def write(path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(tradeoff_rows())


if __name__ == "__main__":
    write(Path(__file__).resolve().parents[2] / "data" / "tables" / "a04-watermark-tradeoff.csv")
