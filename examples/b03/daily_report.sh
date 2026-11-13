#!/usr/bin/env bash
# 日次レポート: ログから 500 の件数を数え、CSV を 1 つ書き出します。
# 使い方: daily_report.sh ログのパス 出力ディレクトリ
set -euo pipefail

log="${1:?使い方: daily_report.sh ログのパス 出力ディレクトリ}"
out_dir="${2:?使い方: daily_report.sh ログのパス 出力ディレクトリ}"

mkdir -p "$out_dir"
tmp=$(mktemp "$out_dir/.report.XXXXXX")
trap 'rm -f "$tmp"' EXIT

# 途中で失敗しても、書きかけのファイルを本番の名前では残さない
echo "path,errors" > "$tmp"
awk '$4 >= 500 {print $3}' "$log" | sort | uniq -c | awk '{print $2 "," $1}' >> "$tmp"
mv "$tmp" "$out_dir/errors.csv"
echo "wrote $out_dir/errors.csv"
