# 有料本文の混入チェックのテストです。
from pathlib import Path

from tests.check_no_paid_text import extract_samples, find_leaks, main

LONG = "ベランダで育てた小さなトマトの苗に、毎朝ていねいに水をあげると、夏には赤い実がたくさんなります。"


def test_見出しとコードと表が除かれる():
    md = f"# 見出しの行はとても長くても対象にしませんので安心してください、三十文字を超えます\n\n```python\n{LONG}\n```\n\n| 列A | 列B |\n| --- | --- |\n\n{LONG}\n"
    assert extract_samples(md) == [LONG]


def test_mermaidとリンクだけの行が除かれる():
    md = "```mermaid\ngraph TD\n```\n\n[とても長いリンクだけの行になっているのでこれは対象外のはずです、確認します](https://example.com/x)\n"
    assert extract_samples(md) == []


def test_30字未満は除かれる():
    assert extract_samples("短い文です。\n") == []


def test_装飾記号は外して返す():
    md = "**ドライバ**は司令塔にあたり、`エグゼキュータ`へ仕事を配って、結果を[集めます](x.md)のでよく覚えておいてください。\n"
    assert extract_samples(md) == ["ドライバは司令塔にあたり、エグゼキュータへ仕事を配って、結果を集めますのでよく覚えておいてください。"]


def test_同じ文があれば1件見つかる(tmp_path: Path):
    (tmp_path / "a.md").write_text(f"前置き\n{LONG}\n", encoding="utf-8")
    hits = find_leaks([LONG], [tmp_path])
    assert hits == [(LONG, tmp_path / "a.md")]


def test_htmlはタグを外して照合する(tmp_path: Path):
    (tmp_path / "a.html").write_text("<p>ベランダで育てた小さなトマトの苗に、<strong>毎朝</strong>ていねいに水をあげると、夏には赤い実がたくさんなります。</p>", encoding="utf-8")
    assert len(find_leaks([LONG], [tmp_path])) == 1


def test_無ければ0件(tmp_path: Path):
    (tmp_path / "a.md").write_text("まったく別の内容です。\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text(LONG, encoding="utf-8")  # 対象外の拡張子
    assert find_leaks([LONG], [tmp_path]) == []


def test_箇条書きと引用の記号は外す():
    md = f"- {LONG}\n* {LONG}\n1. {LONG}\n> {LONG}\n"
    assert extract_samples(md) == [LONG] * 4


def test_html内のliの漏れも見つかる(tmp_path: Path):
    (tmp_path / "a.html").write_text(f"<ul><li>{LONG}</li></ul>", encoding="utf-8")
    samples = extract_samples(f"- {LONG}\n")
    assert len(find_leaks(samples, [tmp_path])) == 1


def test_pyとjsonも調べる(tmp_path: Path):
    (tmp_path / "a.py").write_text(f'X = "{LONG}"', encoding="utf-8")
    (tmp_path / "b.json").write_text(f'{{"text": "{LONG}"}}', encoding="utf-8")
    assert len(find_leaks([LONG], [tmp_path])) == 2


def test_除外ディレクトリは見ない(tmp_path: Path):
    for d in (".git", "node_modules", ".venv", ".superpowers", ".pytest_cache", "__pycache__"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "a.md").write_text(LONG, encoding="utf-8")
    assert find_leaks([LONG], [tmp_path]) == []


def test_同じファイルは重複して数えない(tmp_path: Path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "a.md").write_text(LONG, encoding="utf-8")
    assert len(find_leaks([LONG], [tmp_path, tmp_path / "site"])) == 1


def _pro(tmp_path: Path, body: str) -> Path:
    pro = tmp_path / "pro"
    pro.mkdir()
    (pro / "01.md").write_text(body, encoding="utf-8")
    return pro


def test_main_漏れなしは0(tmp_path: Path):
    pro = _pro(tmp_path, LONG + "\n")
    pub = tmp_path / "pub"
    pub.mkdir()
    (pub / "a.md").write_text("別の内容です。\n", encoding="utf-8")
    assert main(["--pro", str(pro), "--public", str(pub)]) == 0


def test_main_漏れありは1(tmp_path: Path):
    pro = _pro(tmp_path, LONG + "\n")
    pub = tmp_path / "pub"
    pub.mkdir()
    (pub / "a.md").write_text(LONG, encoding="utf-8")
    assert main(["--pro", str(pro), "--public", str(pub)]) == 1


def test_main_proが無いか空なら2(tmp_path: Path):
    pub = tmp_path / "pub"
    pub.mkdir()
    assert main(["--pro", str(tmp_path / "nonexistent"), "--public", str(pub)]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["--pro", str(empty), "--public", str(pub)]) == 2
    short = _pro(tmp_path, "短い。\n")
    assert main(["--pro", str(short), "--public", str(pub)]) == 2
