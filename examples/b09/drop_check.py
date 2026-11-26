"""SFTP などで置かれたファイルを、マニフェスト (名前・サイズ・SHA-256 の一覧) と突き合わせます。"""
import hashlib
import json
from pathlib import Path


def write_manifest(folder):
    """置き終えたあとに、最後に呼ぶ。manifest.json は他のファイルが揃ってから書く。"""
    files = sorted(p for p in Path(folder).iterdir() if p.name not in ("manifest.json", "manifest.json.part"))
    entries = [{"name": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in files]
    part = Path(folder) / "manifest.json.part"
    part.write_text(json.dumps(entries))
    part.rename(Path(folder) / "manifest.json")  # 名前の変更は一瞬なので、書きかけの manifest.json は見えない


def check_drop(folder):
    """問題のあるファイル名の一覧を返す。マニフェストが無ければ、まだ読まない (置いている途中)。"""
    manifest = Path(folder) / "manifest.json"
    if not manifest.exists():
        return None
    problems = []
    for entry in json.loads(manifest.read_text()):
        path = Path(folder) / entry["name"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append(entry["name"])
    return problems
