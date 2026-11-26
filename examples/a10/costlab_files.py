"""小さなファイルの束と、まとめ直し (コンパクション)、圧縮方式の比較。"""
import time
from pathlib import Path

from costlab_layouts import files_and_bytes


def compact(con, src_glob, dst_dir, target_bytes="25MB"):
    """小さなファイルを読み、日付順に並べて、目安の大きさのファイルに書き直します。"""
    Path(dst_dir).mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT * EXCLUDE (day) FROM read_parquet('{src_glob}', hive_partitioning=true) ORDER BY event_date) "
        f"TO '{dst_dir}' (FORMAT parquet, FILE_SIZE_BYTES '{target_bytes}', ROW_GROUP_SIZE 50000)")
    return files_and_bytes(dst_dir)


def codec_report(con, root, codecs=("uncompressed", "snappy", "zstd")):
    """同じ表を圧縮方式だけ変えて書き、サイズ・書く秒・全列を読む秒を返します。"""
    out = {}
    for codec in codecs:
        path = Path(root) / f"codec_{codec}.parquet"
        t0 = time.perf_counter()
        con.execute(f"COPY events TO '{path}' (FORMAT parquet, COMPRESSION {codec})")
        write_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        con.execute(f"SELECT count(*), sum(amount), max(payload) FROM read_parquet('{path}')").fetchall()
        out[codec] = {"bytes": path.stat().st_size, "write_s": write_s, "read_s": time.perf_counter() - t0}
    return out
