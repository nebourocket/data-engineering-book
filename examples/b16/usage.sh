#!/bin/bash
# 第16章: リポジトリの直下で動かす

# 提供の例 (指標層・ファイル渡し・逆 ETL・読み取り専用) を通しで動かし、テストも動かす
python examples/b16/serving_demo.py
pytest examples/b16 -q

# 表の CSV を作り直す
python examples/b16/serving_tables.py
