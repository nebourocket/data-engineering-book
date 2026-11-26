# 練習問題 4 の、直す前のコード (動かさず、読んで問題を探します)。
import csv


def load(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        try:
            save(int(r["id"]))
        except:
            pass
