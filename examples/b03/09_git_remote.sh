#!/usr/bin/env bash
# リモートと PR の流れ (コマンドの例です。テストでは構文だけ確かめます)。
set -euo pipefail

git switch -c feat/orders-etl origin/main
git add etl.py tests/test_etl.py
git commit -m "feat: 注文 CSV を検証して Parquet に書く"
git push -u origin feat/orders-etl
gh pr create --fill
git fetch origin
git rebase origin/main
git push --force-with-lease
