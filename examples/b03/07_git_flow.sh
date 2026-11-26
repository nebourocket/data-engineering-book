#!/usr/bin/env bash
# Git の基本の流れを、使い捨てのリポジトリで一通りたどります。
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

git init -q -b main shop
cd shop
git config user.name "Nebou Rocket"
git config user.email "rocket@example.com"

# 1 コミット = 1 つの目的
printf 'import csv\n' > etl.py
git add etl.py
git commit -q -m "feat: ETL の雛形を追加"

# ブランチを切って作業し、main に戻して取り込む
git switch -q -c feat/validate-orders
printf 'def validate(row):\n    return row\n' >> etl.py
git commit -q -am "feat: 注文行の検証を追加"
git switch -q main
git merge -q --no-ff feat/validate-orders -m "Merge branch 'feat/validate-orders'"
git log --graph --format='%s'

# .gitignore に書いたファイルは add されない
printf '.env\ndata/\n__pycache__/\n' > .gitignore
printf 'API_KEY=dummy-key-0123456789\n' > .env
git add .
git status --short
git commit -q -m "chore: .gitignore を追加"

# 差分を見て、変更を取り消す
printf 'print("debug")\n' >> etl.py
git diff --stat
git restore etl.py
git status --short | wc -l
