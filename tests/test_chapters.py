"""章の検査（型・長さ・表・コードの一致・表記・draft）のテスト。

前半は一時ファイルで各ルールを確かめ、後半は実際の book/basics を検査します。
"""
import os
from pathlib import Path

import pytest

from hooks.chapter_check import BASICS_RANGE, check_chapter, find_hand_tables, is_draft, load_glossary

ROOT = Path(__file__).resolve().parent.parent
CHAPTER_SLUGS = [
    "01-what-is-data-engineering", "02-data-and-computers", "03-linux-shell-git",
    "04-python", "05-sql-basics", "06-sql-advanced", "07-rdb-transactions",
    "08-data-modeling", "09-ingestion", "10-etl-elt-dbt", "11-data-warehouse",
    "12-orchestration", "13-data-quality", "14-cloud-docker-storage",
    "15-streaming-intro", "16-project-and-career",
]


def make_chapter(sections=None, exercises=3, filler=8000, extra="", front=""):
    """検査に通る章の本文を作ります。引数で一部を壊してルール違反を作ります。"""
    parts = [front, "# 第1章 テスト\n\n"]
    parts.append("## この章でできるようになること\n\nできること。\n\n")
    parts.append("## 本論\n\n" + "あ" * filler + "\n\n" + extra)
    parts.append("## よくある失敗\n\n失敗。\n\n## まとめ\n\nまとめ。\n\n## 練習問題\n\n")
    for i in range(exercises):
        parts.append(f"問{i + 1}. 問題です。\n\n??? note \"解答例\"\n    答えです。\n\n")
    parts.append("## 参考文献\n\n- 文献\n")
    text = "".join(parts)
    if sections is not None:
        text = sections(text)
    return text


@pytest.fixture
def env(tmp_path):
    book = tmp_path / "book" / "basics"
    book.mkdir(parents=True)
    (tmp_path / "examples" / "b01").mkdir(parents=True)
    (tmp_path / "data" / "tables").mkdir(parents=True)
    (tmp_path / "data" / "glossary.csv").write_text("正,誤\n冪等,べき等\n", encoding="utf-8")
    return tmp_path


def run(env, text, **kw):
    path = env / "book" / "basics" / "01-test.md"
    path.write_text(text, encoding="utf-8")
    return check_chapter(
        path, examples_dir=env / "examples", tables_dir=env / "data" / "tables",
        glossary=load_glossary(env / "data" / "glossary.csv"), length_range=BASICS_RANGE, prefix="b", **kw)


def test_valid_chapter_passes(env):
    assert run(env, make_chapter()) == []


def test_missing_section_fails(env):
    errors = run(env, make_chapter(sections=lambda t: t.replace("## まとめ", "## おわりに")))
    assert any("見出し" in e for e in errors)


def test_wrong_order_fails(env):
    errors = run(env, make_chapter(sections=lambda t: t.replace("## この章でできるようになること", "## 先頭")))
    assert any("見出し" in e for e in errors)


def test_too_short_fails(env):
    assert any("文字" in e for e in run(env, make_chapter(filler=100)))


def test_too_long_fails(env):
    assert any("文字" in e for e in run(env, make_chapter(filler=17000)))


def test_code_and_table_placeholder_not_counted(env):
    (env / "data" / "tables" / "t.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    code = "```text\n" + "い" * 20000 + "\n```\n\n{{ table(\"t\") }}\n\n"
    assert run(env, make_chapter(extra=code)) == []


def test_few_exercises_fail(env):
    assert any("練習問題" in e for e in run(env, make_chapter(exercises=2)))


def test_hand_written_table_fails(env):
    errors = run(env, make_chapter(extra="| a | b |\n|---|---|\n| 1 | 2 |\n\n"))
    assert any("表" in e for e in errors)


def test_missing_table_fails(env):
    errors = run(env, make_chapter(extra='{{ table("nothing") }}\n\n'))
    assert any("nothing" in e for e in errors)


def test_code_must_be_in_examples(env):
    block = "```python\nprint( 'hi' )\n```\n\n"
    assert any("examples/b01" in e for e in run(env, make_chapter(extra=block)))
    (env / "examples" / "b01" / "hello.py").write_text("import os\n\nprint( 'hi' )\n", encoding="utf-8")
    assert run(env, make_chapter(extra=block)) == []


def test_code_whitespace_normalized(env):
    (env / "examples" / "b01" / "a.sql").write_text("SELECT   1\nFROM t;\n", encoding="utf-8")
    assert run(env, make_chapter(extra="```sql\nSELECT 1 FROM\n  t;\n```\n\n")) == []


def test_code_in_admonition_checked(env):
    errors = run(env, make_chapter(extra="!!! note\n    ```bash\n    ls -la\n    ```\n\n"))
    assert any("examples/b01" in e for e in errors)


def test_text_and_mermaid_exempt(env):
    extra = "```text\n出力例\n```\n\n```mermaid\ngraph TD\n```\n\n"
    assert run(env, make_chapter(extra=extra)) == []


@pytest.mark.parametrize("tag", ["py", "sh", "shell", "zsh", "yml", "docker", "Dockerfile", "{.python}",
                                 "json", "postgresql", "psql", "pgsql", "python title=\"a.py\""])
def test_alias_and_json_tags_are_checked(env, tag):
    errors = run(env, make_chapter(extra=f"```{tag}\nsome_unknown_code_here_12345\n```\n\n"))
    assert any("examples/b01" in e for e in errors), tag


def test_alias_matches_examples(env):
    (env / "examples" / "b01" / "a.sh").write_text("echo hello world\n", encoding="utf-8")
    assert run(env, make_chapter(extra="```sh\necho hello world\n```\n\n")) == []


def test_untagged_block_is_error(env):
    errors = run(env, make_chapter(extra="```\nls\n```\n\n"))
    assert any("言語" in e for e in errors)


def test_unknown_tag_is_error(env):
    errors = run(env, make_chapter(extra="```rust\nfn main() {}\n```\n\n"))
    assert any("rust" in e for e in errors)


def test_output_tag_exempt(env):
    assert run(env, make_chapter(extra="```output\nOK\n```\n\n")) == []


def test_console_checks_only_prompt_lines(env):
    (env / "examples" / "b01" / "a.sh").write_text("ls -la\n", encoding="utf-8")
    ok = "```console\n$ ls -la\ntotal 0\ndrwx foo\n```\n\n"
    assert run(env, make_chapter(extra=ok)) == []
    bad = "```console\n$ rm -rf nothing_here_12345\nignored output\n```\n\n"
    assert any("examples/b01" in e for e in run(env, make_chapter(extra=bad)))


def test_unclosed_fence_is_error(env):
    errors = run(env, make_chapter(extra="```text\nunclosed\n\n"))
    assert any("閉じ" in e for e in errors)


def test_longer_closing_fence_closes(env):
    (env / "examples" / "b01" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert run(env, make_chapter(extra="```python\nx = 1\n`````\n\n")) == []


def test_block_must_be_in_single_file(env):
    (env / "examples" / "b01" / "a.py").write_text("first_statement_line = 1\n", encoding="utf-8")
    (env / "examples" / "b01" / "b.py").write_text("second_statement_line = 2\n", encoding="utf-8")
    block = "```python\nfirst_statement_line = 1\nsecond_statement_line = 2\n```\n\n"
    assert any("examples/b01" in e for e in run(env, make_chapter(extra=block)))


def test_short_block_needs_whole_token_match(env):
    (env / "examples" / "b01" / "a.sh").write_text("echo false\n", encoding="utf-8")
    assert any("examples/b01" in e for e in run(env, make_chapter(extra="```bash\nech\n```\n\n")))
    assert run(env, make_chapter(extra="```bash excerpt\nfalse\n```\n\n")) == []


def test_open_admonition_solution_counts(env):
    text = make_chapter().replace('??? note', '???+ note')
    assert run(env, text) == []


def test_glossary_wrong_term_fails(env):
    errors = run(env, make_chapter(extra="これはべき等な処理です。\n\n"))
    assert any("べき等" in e for e in errors)


def test_draft_is_exempt_from_structure(env):
    draft = "---\nstatus: draft\n---\n\n# 仮\n\nこの章は執筆中です\n"
    assert run(env, draft) == []


def test_draft_still_checks_glossary_and_tables(env):
    draft = "---\nstatus: draft\n---\n\n# 仮\n\nべき等\n"
    assert run(env, draft)


def test_advanced_range_is_parameter(env):
    path = env / "book" / "basics" / "01-test.md"
    path.write_text(make_chapter(filler=8000), encoding="utf-8")
    errors = check_chapter(
        path, examples_dir=env / "examples", tables_dir=env / "data" / "tables",
        glossary=[], length_range=(10000, 20000), prefix="b")
    assert any("文字" in e for e in errors)


def test_find_hand_tables_ignores_code(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("```text\n|---|\n```\n", encoding="utf-8")
    assert find_hand_tables(f.read_text(encoding="utf-8")) == []


# --- 実際の本 ---------------------------------------------------------------

BASICS = ROOT / "book" / "basics"


def test_all_chapter_files_exist():
    for slug in CHAPTER_SLUGS:
        assert (BASICS / f"{slug}.md").exists(), slug


def test_nav_and_index_list_all_chapters():
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    index = (BASICS / "index.md").read_text(encoding="utf-8")
    for slug in CHAPTER_SLUGS:
        assert f"basics/{slug}.md" in nav, slug
        assert f"{slug}.md" in index, slug


@pytest.mark.parametrize("slug", CHAPTER_SLUGS)
def test_basics_chapter(slug):
    errors = check_chapter(
        BASICS / f"{slug}.md", examples_dir=ROOT / "examples", tables_dir=ROOT / "data" / "tables",
        glossary=load_glossary(ROOT / "data" / "glossary.csv"), length_range=BASICS_RANGE, prefix="b")
    assert errors == []


def test_no_hand_written_tables_in_book():
    for md in (ROOT / "book").rglob("*.md"):
        assert find_hand_tables(md.read_text(encoding="utf-8")) == [], md


def test_glossary_columns():
    first = (ROOT / "data" / "glossary.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert first == "正,誤"


@pytest.mark.skipif(os.environ.get("DE_BOOK_FINAL") != "1", reason="DE_BOOK_FINAL=1 のときだけ検査します")
def test_no_drafts_left():
    drafts = [p.name for p in BASICS.glob("[0-9][0-9]-*.md")
              if is_draft(p.read_text(encoding="utf-8"))]
    assert drafts == []


# ---- コードの構文検査（Python・bash・JSON・YAML）----

def syntax_run(env, lang, code, info_extra="", example=None):
    """examples に code（または example）を置いたうえで、1 ブロックだけの章を検査します。"""
    (env / "examples" / "b01" / "a.txt").write_text(example if example is not None else code, encoding="utf-8")
    block = f"```{lang}{info_extra}\n{code}\n```\n\n"
    return run(env, make_chapter(extra=block))


def test_python_valid_passes(env):
    assert syntax_run(env, "python", "x = 1\nprint(x)") == []


def test_python_truncated_fails_even_if_substring(env):
    errors = syntax_run(env, "python", "def f(x):\n    return (x +", example="def f(x):\n    return (x + 1)\n")
    assert any("構文" in e and "python" in e for e in errors)


def test_python_excerpt_marker_skips_syntax(env):
    code = "def f(x):\n    return (x +"
    assert syntax_run(env, "python", code, ' title="f" excerpt', example=code + " 1)\n") == []


def test_bash_valid_passes(env):
    assert syntax_run(env, "bash", "for f in a b; do\n  echo $f\ndone") == []


def test_bash_unclosed_fails(env):
    errors = syntax_run(env, "bash", "for f in a b; do\n  echo $f")
    assert any("構文" in e and "bash" in e for e in errors)


def test_bash_excerpt_marker_skips_syntax(env):
    assert syntax_run(env, "bash", "for f in a b; do\n  echo $f", " excerpt") == []


def test_console_commands_syntax_checked(env):
    assert syntax_run(env, "console", "$ echo hi\nhi") == []
    errors = syntax_run(env, "console", "$ if true; then\nhi")
    assert any("構文" in e for e in errors)


def test_json_valid_passes(env):
    assert syntax_run(env, "json", '{"a": [1, 2]}') == []


def test_json_invalid_fails(env):
    errors = syntax_run(env, "json", '{"a": [1, 2]', example='{"a": [1, 2]}')
    assert any("構文" in e and "json" in e for e in errors)


def test_json_excerpt_marker_skips_syntax(env):
    assert syntax_run(env, "json", '"a": 1,', " excerpt") == []


def test_yaml_valid_passes(env):
    assert syntax_run(env, "yaml", "a:\n  - 1\n  - 2") == []


def test_yaml_invalid_fails(env):
    pytest.importorskip("yaml")
    errors = syntax_run(env, "yaml", "a: [1, 2")
    assert any("構文" in e and "yaml" in e for e in errors)


def test_sql_not_parsed(env):
    assert syntax_run(env, "sql", "SELECT FROM WHERE;") == []


def test_python_uniformly_indented_fragment_passes(env):
    assert syntax_run(env, "python", "    a = 1\n    b = a + 1") == []


def test_bash_uniformly_indented_fragment_passes(env):
    assert syntax_run(env, "bash", "  echo a\n  echo b") == []


# ---- 文を丸ごと写しているか（python・sql・bash）----

def whole_run(env, lang, code, source, fname, info_extra=""):
    """examples に fname で source を置き、code を写したブロック 1 つの章を検査します。"""
    (env / "examples" / "b01" / fname).write_text(source, encoding="utf-8")
    return run(env, make_chapter(extra=f"```{lang}{info_extra}\n{code}\n```\n\n"))


READ_PY = (
    "def read_in_batches(cur):\n"
    "    last_id = 0\n"
    "    while True:\n"
    "        rows = cur.fetchmany(100)\n"
    "        if not rows:\n"
    "            break\n"
    "        yield rows\n"
    "        last_id = rows[-1][0]\n"
)


def test_python_whole_function_passes(env):
    assert whole_run(env, "python", READ_PY, READ_PY, "a.py") == []


def test_python_truncated_function_body_fails(env):
    code = READ_PY.replace("        last_id = rows[-1][0]\n", "")
    errors = whole_run(env, "python", code, READ_PY, "a.py")
    assert any("a.py" in e and "excerpt" in e for e in errors)


def test_python_truncated_body_excerpt_passes(env):
    code = READ_PY.replace("        last_id = rows[-1][0]\n", "")
    assert whole_run(env, "python", code, READ_PY, "a.py", " excerpt") == []


def test_python_body_statements_of_def_pass(env):
    code = "    last_id = 0\n    while True:\n        rows = cur.fetchmany(100)\n        if not rows:\n            break\n        yield rows\n        last_id = rows[-1][0]"
    assert whole_run(env, "python", code, READ_PY, "a.py") == []


def test_python_consecutive_statements_pass(env):
    src = "import os\na = 1\nb = a + 1\nprint(b)\n"
    assert whole_run(env, "python", "a = 1\nb = a + 1", src, "a.py") == []


def test_python_half_statement_fails(env):
    src = "if True:\n    a = 1\n    b = 2\n"
    errors = whole_run(env, "python", "if True:\n    a = 1", src, "a.py")
    assert any("a.py" in e for e in errors)


def test_python_decorated_function_passes(env):
    src = "@cache\ndef f():\n    return 1\n"
    assert whole_run(env, "python", src, src, "a.py") == []


def test_python_in_non_py_file_keeps_substring_rule(env):
    code = READ_PY.replace("        last_id = rows[-1][0]\n", "")
    assert whole_run(env, "python", code, READ_PY, "a.txt") == []


SQL_PY = 'Q1 = """\nSELECT id\nFROM orders\n"""\nQ2 = f"""\nSELECT * FROM {table}\n"""\n'


def test_sql_whole_string_constant_passes(env):
    assert whole_run(env, "sql", "SELECT id\nFROM orders", SQL_PY, "a.py") == []


def test_sql_fstring_placeholder_passes(env):
    assert whole_run(env, "sql", "SELECT * FROM {table}", SQL_PY, "a.py") == []


def test_sql_part_of_string_fails(env):
    errors = whole_run(env, "sql", "SELECT id", SQL_PY, "a.py")
    assert any("a.py" in e and "excerpt" in e for e in errors)


def test_sql_spanning_triple_quotes_fails(env):
    errors = whole_run(env, "sql", "FROM orders\n\"\"\"\nQ2 = f\"\"\"\nSELECT * FROM {table}", SQL_PY, "a.py")
    assert any("a.py" in e for e in errors)


def test_sql_part_of_string_excerpt_passes(env):
    assert whole_run(env, "sql", "SELECT id", SQL_PY, "a.py", " excerpt") == []


def test_sql_in_sql_file_keeps_substring_rule(env):
    assert whole_run(env, "sql", "SELECT id", "SELECT id , name FROM t;\n", "a.sql") == []


SH = "set -e\necho a\necho b\n"


def test_bash_whole_lines_pass(env):
    assert whole_run(env, "bash", "echo a\necho b", SH, "a.sh") == []


def test_bash_mid_line_fails(env):
    errors = whole_run(env, "bash", "echo", SH, "a.sh")
    assert any("a.sh" in e and "excerpt" in e for e in errors)


def test_bash_mid_line_excerpt_passes(env):
    assert whole_run(env, "bash", "echo", SH, "a.sh", " excerpt") == []


def test_python_leading_comment_optional(env):
    src = "# 説明\na = 1\nb = 2\n"
    assert whole_run(env, "python", "a = 1\nb = 2", src, "a.py") == []
    assert whole_run(env, "python", src, src, "a.py") == []
