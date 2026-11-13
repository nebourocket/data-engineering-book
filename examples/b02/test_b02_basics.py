import time_zones
import data_types  # noqa: F401  (import すると実験が走り、例外が出ないことを確かめる)
import row_vs_column
import text_encoding  # noqa: F401


def test_row_and_column_agree():
    assert row_vs_column.total_from_rows == row_vs_column.total_from_columns
    assert row_vs_column.run_length_encode(row_vs_column.columns["category"]) == [("寝具", 2), ("飲み物", 3)]
    assert row_vs_column.run_length_encode([]) == []


def test_encoding_facts():
    assert len(text_encoding.utf8) == 18 and len(text_encoding.cp932) == 12
    assert text_encoding.csv_bytes.startswith(b"\xef\xbb\xbf")
    assert text_encoding.composed != text_encoding.decomposed


def test_timezone_boundaries():
    assert time_zones.moment.astimezone(time_zones.UTC).date().isoformat() == "2026-02-28"
    assert str(time_zones.end - time_zones.start) == "1 day, 0:00:00"
    assert str(time_zones.end.astimezone(time_zones.UTC) - time_zones.start.astimezone(time_zones.UTC)) == "23:00:00"
    assert time_zones.jst_counts[time_zones.day] != time_zones.utc_counts[time_zones.day]
    assert sum(time_zones.jst_counts.values()) == sum(time_zones.utc_counts.values())


def test_float_errors():
    assert 0.1 + 0.2 != 0.3
    assert data_types.total != 1.0
    assert int(0.29 * 100) == 28
    assert len(data_types.float_wrong) > 0
    assert int(data_types.big) != int(float(data_types.big))
