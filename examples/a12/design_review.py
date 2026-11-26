"""第12章: 設計レビューの文書の検査。見出しの欠け・埋めていない雛形・選択肢の少なさ・承認者の欠けを止めます。"""
import re
from pathlib import Path

REQUIRED = ["背景と目的", "目標と非目標", "代替案", "提案", "失敗の仕方", "費用と規模", "移行と戻し方", "未決事項", "決定"]
PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def sections(text):
    """## 見出し -> 本文 の対応 (見出しの順を保つ)。"""
    parts = re.split(r"^## (.+?)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def lint(text):
    """問題の一覧 (空なら合格)。空の文書は合格にしません。"""
    if not text.strip():
        return ["文書が空です"]
    secs = sections(text)
    errors = [f"見出し「{name}」がありません" for name in REQUIRED if name not in secs]
    for name in REQUIRED:
        body = secs.get(name)
        if body is None:
            continue
        if not PLACEHOLDER.sub("", body).strip(" -\n"):
            errors.append(f"「{name}」が空です")
        elif PLACEHOLDER.search(body):
            errors.append(f"「{name}」に雛形の <…> が残っています")
    options = re.findall(r"^- 案 [A-Z]:", secs.get("代替案", ""), flags=re.M)
    if "代替案" in secs and len(options) < 2:
        errors.append("代替案が 2 つ未満です (現状維持を含めて 2 つ以上)")
    decision = secs.get("決定", "")
    if "決定" in secs:
        for label, message in (("承認者", "承認者がいません"), ("結論", "結論がありません")):
            if not re.search(rf"^- {label}: \S", decision, flags=re.M):
                errors.append(message)
    pending = secs.get("未決事項", "")
    for line in pending.splitlines():
        if line.startswith("- ") and "回答する人:" not in line and line.strip() != "- なし":
            errors.append(f"未決事項に回答する人がいません: {line[:30]}")
    return errors


def lint_file(path):
    return lint(Path(path).read_text(encoding="utf-8"))
