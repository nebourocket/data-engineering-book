"""テーブルフォーマットが無い「ただのフォルダ」で起きる困りごとを、実際に起こして数えます。"""
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from lake_events import make_batch


def write_files(root, batch_nos):
    """バッチごとに 1 つの Parquet ファイルを置きます。"""
    for n in batch_nos:
        pq.write_table(make_batch(n, rows=10), root / f"part-{n}.parquet")


def rows_visible(root):
    """いまフォルダを読んだ読み手に見える行数。"""
    return ds.dataset(root, format="parquet").count_rows()


def half_written_view(root):
    """3 ファイルを書く途中 (2 つ目まで) で読んだ行数と、書き終えたあとの行数。"""
    write_files(root, [0, 1])
    midway = rows_visible(root)
    write_files(root, [2])
    return midway, rows_visible(root)


def silent_nulls(root):
    """列名が途中で変わった 2 つのファイルを読むと、片方の列が静かに空になります。"""
    pq.write_table(pa.table({"id": [1, 2], "price": [100, 200]}), root / "old.parquet")
    pq.write_table(pa.table({"id": [3, 4], "price_yen": [300, 400]}), root / "new.parquet")
    first = ds.dataset(root / "old.parquet", format="parquet")
    merged = ds.dataset([str(root / "old.parquet"), str(root / "new.parquet")],
                        schema=first.schema, format="parquet").to_table()
    return merged.column("price").to_pylist()


def files_to_rewrite_for_delete(root, customer_id):
    """ある顧客の行を消すために、書き換えが要るファイルの数と全ファイル数。"""
    touched = 0
    paths = sorted(root.glob("*.parquet"))
    for path in paths:
        table = pq.read_table(path)
        if customer_id in table.column("customer_id").to_pylist():
            touched += 1
    return touched, len(paths)
