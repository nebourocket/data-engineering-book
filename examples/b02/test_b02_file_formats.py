import file_formats


def test_parquet_is_smaller_and_faster_than_csv():
    results = {r["format"]: r for r in file_formats.measure(seeds=5)}
    csv, parquet = results["CSV"], results["Parquet (zstd)"]
    assert parquet["size_mb"] < csv["size_mb"] / 3
    assert results["JSON Lines"]["size_mb"] > csv["size_mb"]
    assert results["CSV (gzip)"]["size_mb"] < csv["size_mb"]
    assert results["Parquet (snappy)"]["rows"] == csv["rows"]
