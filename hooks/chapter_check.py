"""章の検査（型・長さ・表・コードの一致・表記・draft）。

MkDocs には依存しません（応用編の非公開リポジトリからも import します）。
長さの範囲と examples の接頭辞（基礎編は b、応用編は a）は引数で変えられます。
"""
import csv
import re
from pathlib import Path

BASICS_RANGE = (7000, 16000)
ADVANCED_RANGE = (10000, 20000)

FIRST_H2 = "この章でできるようになること"
LAST_H2 = ["よくある失敗", "まとめ", "練習問題", "参考文献"]
MIN_EXERCISES = 3
# 検査するコードブロックの言語（別名は ALIASES で正規化します）。
CHECKED_LANGS = {"python", "sql", "bash", "yaml", "toml", "dockerfile", "ini", "json"}
ALIASES = {
    "py": "python", "python3": "python",
    "sh": "bash", "shell": "bash", "zsh": "bash",
    "yml": "yaml", "docker": "dockerfile",
    "postgresql": "sql", "pgsql": "sql", "psql": "sql",
}
# 出力や図なので examples との一致を求めない言語。
EXEMPT_LANGS = {"text", "mermaid", "output"}
# 短いブロックは、前後が空白（または端）の語としてだけ一致を認めます。
SHORT_BLOCK = 20

TABLE_PLACEHOLDER_RE = re.compile(r'\{\{\s*table\("([a-z0-9-]+)"\)\s*\}\}')
FENCE_OPEN_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})[ \t]*(.*?)\s*$")
FRONT_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$|^\s*\|\s*:?-{3,}:?\s*\|?\s*$")


def split_front_matter(text: str):
    """(front matter の文字列, 本文) を返します。無ければ front matter は空です。"""
    m = FRONT_RE.match(text)
    return (m.group(1), text[m.end():]) if m else ("", text)


def is_draft(text: str) -> bool:
    front, _ = split_front_matter(text)
    return re.search(r"^status:\s*draft\s*$", front, re.M) is not None


def load_glossary(path: Path) -> list[tuple[str, str]]:
    """glossary.csv（列 正,誤）を [(正, 誤), ...] で返します。"""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return [(r["正"], r["誤"]) for r in csv.DictReader(f)]


def parse_fences(body: str):
    """本文を (prose, blocks, errors) に分けます。

    prose はコードブロックを除いた本文。blocks は (indent, info, code) の一覧。
    閉じ側の囲いは開きと同じ文字で、開き以上の長さなら閉じます（CommonMark）。
    閉じていないブロックは errors に入れます。
    """
    prose, blocks, errors = [], [], []
    lines = body.split("\n")
    i = 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m or (m.group(2)[0] == "`" and "`" in m.group(3)):
            prose.append(lines[i])
            i += 1
            continue
        indent, fence, info = m.groups()
        close = re.compile(rf"^[ \t]*{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$")
        j = i + 1
        while j < len(lines) and not close.match(lines[j]):
            j += 1
        if j >= len(lines):
            errors.append(f"コード: {i + 1} 行目のコードブロックが閉じていません")
            break
        blocks.append((indent, info, "\n".join(lines[i + 1:j])))
        i = j + 1
    return "\n".join(prose), blocks, errors


def _strip_code(body: str) -> str:
    return parse_fences(body)[0]


def _lang(info: str) -> str:
    """info 文字列から言語名を取り出し、別名を正規化します（無ければ空文字）。"""
    info = info.strip()
    if info.startswith("{"):
        m = re.search(r"\.([A-Za-z0-9_+-]+)", info)
        return ALIASES.get(m.group(1).lower(), m.group(1).lower()) if m else ""
    word = info.split()[0].lower() if info.split() else ""
    return ALIASES.get(word, word)


def _console_commands(code: str) -> str:
    """console ブロックから、`$ ` で始まる行（と行末 \\ で続く行）だけを取り出します。"""
    out, cont = [], False
    for ln in code.split("\n"):
        if ln.startswith("$ "):
            out.append(ln[2:])
            cont = ln.rstrip().endswith("\\")
        elif cont:
            out.append(ln)
            cont = ln.rstrip().endswith("\\")
    return "\n".join(out)


def find_hand_tables(text: str) -> list[str]:
    """コードブロックの外にある手書きの Markdown 表（区切り行）を返します。"""
    return [ln for ln in _strip_code(text).splitlines() if "|" in ln and TABLE_SEP_RE.match(ln)]


def _dedent(code: str, indent: str) -> str:
    return "\n".join(ln[len(indent):] if ln.startswith(indent) else ln for ln in code.split("\n"))


def _norm(s: str) -> str:
    return " ".join(s.split())


def check_chapter(path, *, examples_dir, tables_dir, glossary, length_range, prefix="b") -> list[str]:
    """章 1 本を検査し、問題の一覧（空なら合格）を返します。"""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    _, body = split_front_matter(text)
    prose = _strip_code(body)
    errors = []

    # 表記と表は draft でも検査します。
    for correct, wrong in glossary:
        if wrong and wrong in prose:
            errors.append(f"表記: 「{wrong}」は「{correct}」に直してください")
    for line in find_hand_tables(body):
        errors.append(f"表: 手書きの表があります（CSV と table() を使います）: {line.strip()}")
    for name in TABLE_PLACEHOLDER_RE.findall(body):
        if not (Path(tables_dir) / f"{name}.csv").exists():
            errors.append(f"表: data/tables/{name}.csv がありません")

    if is_draft(text):
        return errors

    # 見出しの型（コードブロック内の # を除いた h2 の並び）
    h2 = re.findall(r"^## (.+?)\s*$", prose, re.M)
    if not h2 or h2[0] != FIRST_H2 or h2[-4:] != LAST_H2 or len(h2) < 6:
        errors.append(
            f"見出し: 「{FIRST_H2}」で始まり、本論の節を挟んで {' / '.join(LAST_H2)} で終えてください（現在: {h2}）")

    # 長さ（コードブロックと表の記号を除いた空白なしの文字数）
    n = len(re.sub(r"\s+", "", TABLE_PLACEHOLDER_RE.sub("", prose)))
    lo, hi = length_range
    if not lo <= n <= hi:
        errors.append(f"文字数: {n} 文字です（{lo}〜{hi} 文字）")

    # 練習問題
    m = re.search(r"^## 練習問題\s*$(.*?)(?=^## |\Z)", prose, re.M | re.S)
    count = len(re.findall(r'^\s*\?\?\?\+? note "解答例"', m.group(1), re.M)) if m else 0
    if count < MIN_EXERCISES:
        errors.append(f"練習問題: 解答例（??? note \"解答例\"）が {count} 個です（{MIN_EXERCISES} 個以上）")

    # コードの一致
    num = re.match(r"(\d+)-", path.name)
    _, blocks, fence_errors = parse_fences(body)
    errors += fence_errors
    if num:
        label = f"examples/{prefix}{num.group(1)}/"
        ex_dir = Path(examples_dir) / f"{prefix}{num.group(1)}"
        files = []
        if ex_dir.is_dir():
            files = [_norm(f.read_text(encoding="utf-8", errors="ignore"))
                     for f in sorted(ex_dir.rglob("*")) if f.is_file()]
        for indent, info, raw in blocks:
            lang = _lang(info)
            if not lang:
                errors.append("コード: 言語の指定がないコードブロックがあります（出力は text を使います）")
                continue
            code = _dedent(raw, indent)
            if lang == "console":
                lang, code = "bash", _console_commands(code)
            elif lang in EXEMPT_LANGS:
                continue
            elif lang not in CHECKED_LANGS:
                errors.append(f"コード: 言語「{lang}」は使えません（{', '.join(sorted(CHECKED_LANGS | EXEMPT_LANGS))}, console）")
                continue
            code = _norm(code)
            if code and not any(_contains(f, code) for f in files):
                errors.append(f"コード: {lang} のブロックが {label} の 1 つのファイルにありません: {code[:40]}…")
    return errors


def _contains(file_text: str, code: str) -> bool:
    """1 つのファイルに code が続けて含まれるか。短い code は語として一致させます。"""
    if len(code) >= SHORT_BLOCK:
        return code in file_text
    return re.search(rf"(?<!\S){re.escape(code)}(?!\S)", file_text) is not None
