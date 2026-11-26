#!/usr/bin/env bash
# 練習問題の解答例。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"

awk '$3 ~ /^\/products\// {print $3}' access.log | sort | uniq -c | sort -rn
