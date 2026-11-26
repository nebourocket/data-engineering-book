"""第10章のフィクスチャ: このフォルダの .py を import できるようにします。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
