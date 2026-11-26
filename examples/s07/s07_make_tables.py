"""第 7 章の表 (data/tables/s07-*.csv のうち、データを含むもの) をコードから作ります。

横持ち・縦持ち・平らにした注文の表は、手で写すと数字が揺れるので、このスクリプトが CSV に書き出します。
"""
import contextlib
import csv
import importlib.util
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TABLES = HERE.parents[1] / "data" / "tables"
sys.path.insert(0, str(HERE))


def _load(name):
    """s07_ のスクリプトを読み込みます (読み込み時の print は捨てます)。"""
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    return module


def build() -> dict[str, list[list[str]]]:
    """{CSV 名: 見出し付きの文字列の行} を返します。None は空欄にします。"""
    wide_long = _load("s07_wide_long")
    flatten = _load("s07_flatten").flatten
    data = json.loads((HERE / "s07_shop_orders.json").read_text(encoding="utf-8"))

    def grid(rows):
        header = list(rows[0])
        return [header] + [["" if r[k] is None else str(r[k]) for k in header] for r in rows]

    return {
        "s07-wide": grid(wide_long.wide),
        "s07-long": grid(wide_long.long_rows),
        "s07-flat-orders": grid(flatten(data)),
    }


def write_all(out_dir: Path = TABLES) -> None:
    for name, rows in build().items():
        with open(out_dir / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
            csv.writer(f, lineterminator="\n").writerows(rows)


if __name__ == "__main__":
    write_all()
