import pytest

from hooks.tables import expand_tables, render_table


def write(tmp_path, name, text):
    (tmp_path / f"{name}.csv").write_text(text, encoding="utf-8")


def test_render_basic(tmp_path):
    write(tmp_path, "t", "a,b\n1,2\n")
    assert render_table("t", tmp_path) == "| a | b |\n| --- | --- |\n| 1 | 2 |\n"


def test_render_escapes_pipe(tmp_path):
    write(tmp_path, "t", 'a,b\n"x|y",2\n')
    assert "x\\|y" in render_table("t", tmp_path)


def test_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_table("nothing", tmp_path)


def test_expand_replaces_all_and_keeps_text(tmp_path):
    write(tmp_path, "t", "a,b\n1,2\n")
    out = expand_tables('前\n{{ table("t") }}\n後', tmp_path)
    assert out.startswith("前\n") and out.endswith("\n後")
    assert "| a | b |" in out and "{{" not in out


def test_expand_ignores_other_braces(tmp_path):
    assert expand_tables("{{ other }}", tmp_path) == "{{ other }}"


def test_bom_is_stripped(tmp_path):
    (tmp_path / "t.csv").write_bytes(b"\xef\xbb\xbfa,b\n1,2\n")
    assert render_table("t", tmp_path).startswith("| a | b |")


def test_column_mismatch_raises_with_file_and_row(tmp_path):
    write(tmp_path, "t", "a,b\n1,2\n3\n")
    with pytest.raises(ValueError) as e:
        render_table("t", tmp_path)
    assert "t.csv" in str(e.value) and "3" in str(e.value)


def test_empty_csv_raises(tmp_path):
    write(tmp_path, "t", "")
    with pytest.raises(ValueError, match="t.csv"):
        render_table("t", tmp_path)
