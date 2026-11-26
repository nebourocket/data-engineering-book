"""小さいファイル問題の実験: 同じ行を 1 ファイルに置くか、小さく分けて置くかで大きさを比べます。

ねぼすけ商店の行動ログ 4,040 行を、(a) 1 ファイル、(b) 100 行ずつ 41 ファイルに書き、
ファイル数・合計バイト数・DuckDB で hive_partitioning つきに読んだ結果を返します。
"""
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import generate  # noqa: E402


def write_files(rows, directory, rows_per_file):
    directory.mkdir(parents=True, exist_ok=True)
    for i, start in enumerate(range(0, len(rows), rows_per_file)):
        pq.write_table(pa.Table.from_pylist(rows[start:start + rows_per_file]),
                       directory / f"part-{i:04d}.parquet")


def summarize(directory):
    files = sorted(directory.glob("*.parquet"))
    count = duckdb.sql(f"SELECT count(*) FROM read_parquet('{directory}/*.parquet')").fetchall()[0][0]
    return {"files": len(files), "bytes": sum(f.stat().st_size for f in files), "rows": count}


def compare(base):
    rows = generate()["events"]
    write_files(rows, base / "one", rows_per_file=len(rows))
    write_files(rows, base / "small", rows_per_file=100)
    return {"one": summarize(base / "one"), "small": summarize(base / "small")}


def hive_count(base, dt):
    """dt=YYYY-MM-DD のフォルダに分けて置き、パスの dt を列として読んで 1 日分だけ数えます。"""
    rows = generate()["events"]
    by_day = {}
    for row in rows:
        by_day.setdefault(row["event_time"][:10], []).append(row)
    for day, day_rows in by_day.items():
        write_files(day_rows, base / f"dt={day}", rows_per_file=len(day_rows))
    sql = (f"SELECT count(*) FROM read_parquet('{base}/*/*.parquet', hive_partitioning = true) "
           f"WHERE dt = '{dt}'")
    return duckdb.sql(sql).fetchall()[0][0], len(by_day)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        for name, stats in compare(Path(tmp)).items():
            print(name, stats)
