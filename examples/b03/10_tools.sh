#!/usr/bin/env bash
# 圧縮したログの読み方、ファイルの大きさの調べ方。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

gzip -c "$here/access.log" > access.log.gz
zcat access.log.gz | wc -l
zgrep -c ' 500 ' access.log.gz
ls -l access.log.gz | awk '{print $1, $9}'
du -k "$here/access.log" | awk '{print ($1 > 0) ? "サイズあり" : "空"}'
df -P . | awk 'NR == 2 {print "使用率の列:", $5 ~ /%$/}'
