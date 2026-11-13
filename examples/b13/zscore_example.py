"""標準偏差と Z スコアの手計算の例。5 日分の件数から、1 ステップずつ計算して表にします。

使い方: python examples/b13/zscore_example.py [CSV の出力先]
出力先を渡すと、本文の表 (data/tables/b13-zscore-example.csv) を書き出します。
"""
import csv
import statistics
import sys

BASELINE = [20, 22, 21, 23, 19]  # 直近 5 日の件数
TODAY = 30  # 今日の件数


def worked_example(baseline=BASELINE, today=TODAY):
    mean = sum(baseline) / len(baseline)
    squares = [(x - mean) ** 2 for x in baseline]
    variance = sum(squares) / (len(baseline) - 1)  # 標本分散 (n ではなく n-1 で割る)
    sd = variance ** 0.5
    return {"mean": mean, "squares": squares, "variance": variance, "sd": sd,
            "z": (today - mean) / sd}


def write_table(path):
    w = worked_example()
    with open(path, "w", encoding="utf-8", newline="") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(["日", "件数", "平均との差", "差の2乗"])
        for i, (x, sq) in enumerate(zip(BASELINE, w["squares"]), start=1):
            out.writerow([f"{i} 日目", x, f"{x - w['mean']:g}", f"{sq:g}"])
        out.writerow(["合計", sum(BASELINE), "0", f"{sum(w['squares']):g}"])


if __name__ == "__main__":
    w = worked_example()
    assert abs(w["sd"] - statistics.stdev(BASELINE)) < 1e-12  # 標準ライブラリの結果と一致
    print(f"平均 {w['mean']:g}  差の2乗の合計 {sum(w['squares']):g}  分散 {w['variance']:g}  "
          f"標準偏差 {w['sd']:.2f}  Z = ({TODAY} - {w['mean']:g}) / {w['sd']:.2f} = {w['z']:.2f}")
    if len(sys.argv) > 1:
        write_table(sys.argv[1])
