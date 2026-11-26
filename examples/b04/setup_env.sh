#!/usr/bin/env bash
# 仮想環境を作り、依存を入れて、入れた版を書き出す (コマンドの例です。テストでは構文だけ確かめます)。
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
python -m pip install "pyarrow==26.0.1" "boto3==1.44.2"
python -m pip freeze > requirements.txt
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
