#!/usr/bin/env bash
# clone・pull・stash・rebase の衝突の直し方。手元にリモート代わりの bare リポジトリを作って試します。
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

git init -q --bare -b main remote.git
git clone -q remote.git alice 2> /dev/null
git clone -q remote.git bob 2> /dev/null
for who in alice bob; do
    git -C "$who" config user.name "$who"
    git -C "$who" config user.email "$who@example.com"
done

# alice が最初のコミットを push し、bob が受け取る
printf 'batch_size = 100\n' > alice/etl.py
git -C alice add etl.py
git -C alice commit -q -m "feat: ETL の雛形を追加"
git -C alice push -q -u origin main 2> /dev/null
git -C bob pull -q origin main
cat bob/etl.py

# 2 人が同じ行を別々に変える。先に alice が push する
printf 'batch_size = 500\n' > alice/etl.py
git -C alice commit -q -am "fix: バッチを 500 に"
git -C alice push -q
printf 'batch_size = 1000\n' > bob/etl.py
git -C bob commit -q -am "fix: バッチを 1000 に"

# bob の作業中の変更は、stash で一時的に避けておける
printf 'memo\n' > bob/notes.txt
git -C bob add notes.txt
git -C bob stash -q
git -C bob stash list | wc -l

# bob が rebase で取り込むと、衝突して止まる
git -C bob pull --rebase -q origin main > /dev/null 2>&1 || true
git -C bob status --short
# 衝突を直す: どちらの値にするかを決めて書き、add して続ける
printf 'batch_size = 1000\n' > bob/etl.py
git -C bob add etl.py
GIT_EDITOR=true git -C bob rebase --continue > /dev/null 2>&1 || true
git -C bob log --format='%s'
git -C bob stash pop -q
git -C bob status --short
