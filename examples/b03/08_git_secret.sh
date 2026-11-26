#!/usr/bin/env bash
# 秘密を commit してしまったとき。履歴に残る様子と、まずやることを確かめます。
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

git init -q -b main shop
cd shop
git config user.name "Nebou Rocket"
git config user.email "rocket@example.com"

printf 'API_KEY=dummy-key-0123456789\n' > .env
git add .env
git commit -q -m "add env"

# 気づいて消しても、過去のコミットには鍵が残っている
git rm -q --cached .env
echo '.env' > .gitignore
git add .gitignore
git commit -q -m "stop tracking .env"
git log --oneline | wc -l
git show HEAD~1:.env
git log --all --format='%s' -S'dummy-key-0123456789'
