"""第6章のフィクスチャ: 公開側の共通データ (ねぼすけ商店) を import できるようにします。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
