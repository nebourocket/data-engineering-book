"""ETL の入力 (JSON Lines の行動ログ) を、ねぼすけ商店のデータから作ります。

使い方: python examples/b14/make_input.py examples/b14/data/events.jsonl
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import generate  # noqa: E402

if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = generate()["events"]
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print(f"{len(rows)} 行を {out} に書きました")
