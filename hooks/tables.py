"""CSV から Markdown の表を作る MkDocs hook。

render_table / expand_tables は MkDocs に依存しません（別リポジトリのビルドからも import します）。
"""
import csv
import re
from pathlib import Path

TABLE_RE = re.compile(r'\{\{\s*table\("([a-z0-9-]+)"\)\s*\}\}')


def _cell(value: str) -> str:
    # 表が崩れないよう、縦線はエスケープし改行は空白にします。
    return value.replace("|", "\\|").replace("\n", " ")


def render_table(name: str, tables_dir: Path) -> str:
    """tables_dir/<name>.csv（UTF-8、BOM は無視、1行目が見出し）を Markdown の表にして返します。"""
    path = Path(tables_dir) / f"{name}.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:  # 無ければ FileNotFoundError
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"{path.name}: CSV が空です（見出し行がありません）")
    header, body = rows[0], rows[1:]
    for i, row in enumerate(body, start=2):
        if len(row) != len(header):
            raise ValueError(
                f"{path.name}: {i} 行目の列数が {len(row)} です（見出しは {len(header)} 列）")
    lines = ["| " + " | ".join(_cell(c) for c in header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in body:
        lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return "\n".join(lines) + "\n"


def expand_tables(markdown: str, tables_dir: Path) -> str:
    """本文中の {{ table("名前") }} をすべて表に置き換えます。"""
    return TABLE_RE.sub(lambda m: render_table(m.group(1), tables_dir), markdown)


def on_page_markdown(markdown, page, config, files):
    tables_dir = Path(config["config_file_path"]).parent / "data" / "tables"
    return expand_tables(markdown, tables_dir)
