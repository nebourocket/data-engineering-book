"""行の削除を「ファイルの書き直し (copy-on-write)」と「削除の印だけ書く (merge-on-read)」で比べる小さな模型。

実際の Iceberg の位置削除ファイルは (file_path, pos) の 2 列を持つ Parquet です。ここでは同じ形を
pyarrow で作り、書いたバイト数を数えます。Delta Lake の削除ベクトルは同じ考え方で、印をビットマップに持ちます。
"""
import random
import time

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def write_base(path, rows):
    """event_id と、ばらけた文字列 (24 桁の 16 進数) を持つ 1 ファイルを書き、そのバイト数を返します。"""
    rng = random.Random(1)
    table = pa.table({"event_id": list(range(rows)),
                      "payload": [f"{rng.getrandbits(96):024x}" for _ in range(rows)]})
    pq.write_table(table, path)
    return path.stat().st_size


def cow_delete(src, dst, drop_ids):
    """copy-on-write: 残す行だけで新しいファイルを丸ごと書き直し、そのバイト数を返します。"""
    table = pq.read_table(src)
    keep = pc.invert(pc.is_in(table.column("event_id"), value_set=pa.array(drop_ids)))
    pq.write_table(table.filter(keep), dst)
    return dst.stat().st_size


def mor_delete(src, delete_file, drop_ids):
    """merge-on-read: 消す行の位置 (何行目か) だけを別のファイルに書き、そのバイト数を返します。"""
    table = pq.read_table(src, columns=["event_id"])
    positions = [i for i, v in enumerate(table.column("event_id").to_pylist()) if v in set(drop_ids)]
    pq.write_table(pa.table({"file_path": [src.name] * len(positions), "pos": positions}), delete_file)
    return delete_file.stat().st_size


def read_with_deletes(src, delete_file):
    """読むときに削除ファイルを突き合わせます。読み手の仕事が 1 つ増えます。"""
    table = pq.read_table(src)
    dropped = set(pq.read_table(delete_file).column("pos").to_pylist())
    keep = [i for i in range(table.num_rows) if i not in dropped]
    return table.take(keep)


def read_with_many_deletes(src, delete_files):
    """削除ファイルを全部読んで突き合わせます。削除ファイルが増えるほど、開くファイルが増えます。"""
    table = pq.read_table(src)
    positions = []
    for f in delete_files:
        positions += pq.read_table(f).column("pos").to_pylist()
    keep = pc.invert(pc.is_in(pa.array(range(table.num_rows)), value_set=pa.array(positions, pa.int64())))
    return table.filter(keep)


def read_cost(work, base, delete_counts=(0, 1, 10, 100), rows_per_delete=10):
    """削除ファイルが 0・1・10・100 個のときの、読む時間 (3 回の最短) と開くファイル数。

    1 回の削除ごとに小さな削除ファイルが 1 つできる、という前提です。
    """
    out = []
    for count in delete_counts:
        files = []
        for n in range(count):
            f = work / f"del-{count}-{n}.parquet"
            first = n * rows_per_delete
            pq.write_table(pa.table({"file_path": [base.name] * rows_per_delete,
                                     "pos": list(range(first, first + rows_per_delete))}), f)
            files.append(f)
        best = None
        for _ in range(3):
            start = time.perf_counter()
            kept = read_with_many_deletes(base, files)
            elapsed = time.perf_counter() - start
            best = elapsed if best is None else min(best, elapsed)
        out.append({"delete_files": count, "files_opened": 1 + count, "rows": kept.num_rows, "seconds": best})
    return out
