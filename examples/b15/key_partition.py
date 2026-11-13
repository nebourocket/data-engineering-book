"""キーからパーティションが決まる仕組みの、小さな計算例です。

confluent-kafka (librdkafka) の既定 (partitioner=consistent_random) は、キーの文字列を UTF-8 のバイト列にして
CRC32 というハッシュ関数にかけ、パーティション数で割った余りを行き先にします (キーがあるときの話です)。
ハッシュ関数は、同じ入力から必ず同じ数を作り、入力が少し違うと数が大きく変わる関数です。
"""
import csv
import zlib
from pathlib import Path


def key_to_partition(key, partitions=3):
    return zlib.crc32(key.encode("utf-8")) % partitions


def write_table(path, keys=("91", "166", "200", "250"), partitions=3):
    """data/tables/b15-key-partition.csv を書きます。本文の表はこのファイルから作ります。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["キー (顧客番号)", "CRC32 (10 進数)", f"{partitions} で割った余り (行き先のパーティション)"])
        for key in keys:
            writer.writerow([key, zlib.crc32(key.encode("utf-8")), key_to_partition(key, partitions)])


if __name__ == "__main__":
    write_table(Path(__file__).resolve().parents[2] / "data" / "tables" / "b15-key-partition.csv")
