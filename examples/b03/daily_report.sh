#!/usr/bin/env bash
# 日次レポート: 指定した日のログから 500 以上の件数を数え、CSV を 1 つ書き出します。
# 使い方: daily_report.sh ログのパス 出力ディレクトリ 日付(YYYY-MM-DD)
set -euo pipefail

log="${1:?使い方: daily_report.sh ログのパス 出力ディレクトリ 日付}"
out_dir="${2:?使い方: daily_report.sh ログのパス 出力ディレクトリ 日付}"
day="${3:?使い方: daily_report.sh ログのパス 出力ディレクトリ 日付}"

[ -r "$log" ] || { echo "ログが読めません: $log" >&2; exit 1; }
mkdir -p "$out_dir"
tmp=$(mktemp "$out_dir/.report.XXXXXX")
trap 'rm -f "$tmp"' EXIT

# 途中で失敗しても、書きかけのファイルを本番の名前では残さない
echo "path,errors" > "$tmp"
{ grep "^$day" "$log" || true; } | awk '$4 >= 500 {print $3}' | sort | uniq -c | awk '{print $2 "," $1}' >> "$tmp"   # 該当日が 0 件でも失敗にしない
chmod 644 "$tmp"   # mktemp は 0600 で作るので、読む人のために権限を広げる
mv "$tmp" "$out_dir/errors-$day.csv"
echo "wrote $out_dir/errors-$day.csv"
