"""非公開リポジトリの本文が、公開側に混ざっていないか調べます。

使い方:
  python tests/check_no_paid_text.py --pro ../data-engineering-book-pro/chapters --public . --site site

非公開の章から「30字以上の地の文」を抜き出し、公開リポジトリと site/ の中に同じ文がないか探します。
CI は非公開リポジトリを読めないので、このチェックは手元（公開前と応用編の更新時）で回します。

限界: 文の一部だけが言い換えられた場合や、1行が途中で折り返された場合は見つけられません。
Markdown の装飾 (**, `, リンク) と HTML のタグは外してから照合しますが、それ以上の正規化はしません。
"""
import argparse
import html
import re
import sys
from pathlib import Path

MIN_LEN = 30
SUFFIXES = {".md", ".html", ".js", ".csv", ".json", ".py"}
SKIP_DIRS = {".git", "node_modules", ".venv", ".superpowers", ".pytest_cache", "__pycache__"}


def strip_markup(text: str) -> str:
    """インラインの Markdown 装飾を外します（リンクは表示文字だけ残す）。"""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[*`]", "", text)


def extract_samples(md_text: str) -> list[str]:
    """見出し・コード・表・Mermaid・リンクだけの行を除き、30字以上の行を返します。"""
    samples = []
    in_fence = False
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence or not s:
            continue
        if s.startswith(("#", "|", "<!--", ":::")):
            continue
        # リンクだけの行（[text](url) の1つだけ）は本文ではないので除きます。
        if re.fullmatch(r"[-*]?\s*!?\[[^\]]*\]\([^)]*\)", s):
            continue
        # 箇条書き・番号付き・引用の記号は HTML では消えるので外します。
        s = re.sub(r"^(?:>\s*)*(?:[-*+]\s+|\d+[.)]\s+)?", "", s)
        s = strip_markup(s)
        if len(s) >= MIN_LEN:
            samples.append(s)
    return samples


def _searchable_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".html":
        text = html.unescape(re.sub(r"<[^>]*>", "", text))
    elif path.suffix == ".md":
        text = strip_markup(text)
    return text


def find_leaks(samples: list[str], roots: list[Path]) -> list[tuple[str, Path]]:
    """samples が含まれるファイルを (文, ファイル) の組で返します。"""
    hits = []
    seen = set()
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.suffix not in SUFFIXES or not path.is_file():
                continue
            if SKIP_DIRS & set(path.relative_to(root).parts):
                continue
            real = path.resolve()
            if real in seen:  # --public . と --site site で同じファイルを二重に数えません
                continue
            seen.add(real)
            text = _searchable_text(path)
            hits.extend((s, path) for s in samples if s in text)
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pro", required=True, type=Path, help="非公開リポジトリの chapters ディレクトリ")
    ap.add_argument("--public", required=True, type=Path, help="公開リポジトリのルート")
    ap.add_argument("--site", type=Path, help="mkdocs build の出力 (site/)")
    args = ap.parse_args(argv)

    if not args.pro.is_dir():
        print(f"エラー: --pro がディレクトリではありません: {args.pro}", file=sys.stderr)
        return 2
    samples = []
    for md in sorted(args.pro.glob("*.md")):
        samples.extend(extract_samples(md.read_text(encoding="utf-8")))
    if not samples:
        print(f"エラー: {args.pro} から照合する文を1件も取れませんでした（何も調べていません）", file=sys.stderr)
        return 2
    roots = [args.public] + ([args.site] if args.site else [])
    hits = find_leaks(samples, roots)
    if hits:
        for sample, path in hits:
            print(f"漏れ: {path}\n  {sample}")
        return 1
    print(f"漏れはありません（調べた文: {len(samples)} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
