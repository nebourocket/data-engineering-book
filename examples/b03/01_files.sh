#!/usr/bin/env bash
# ファイルとディレクトリの基本操作。使い捨ての作業ディレクトリの中だけで動かします。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

mkdir -p data/raw data/clean
cp "$here/access.log" data/raw/2026-11-02.log
find data -type d | sort

wc -l < data/raw/2026-11-02.log
head -n 3 data/raw/2026-11-02.log
tail -n 2 data/raw/2026-11-02.log

mv data/raw/2026-11-02.log data/raw/access-20261102.log
ls data/raw
rm data/raw/access-20261102.log
ls data/raw | wc -l
