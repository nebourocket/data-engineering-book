#!/usr/bin/env bash
# ねぼすけ商店のアクセスログを、パイプとリダイレクトで集計します。
# ログの形式: 時刻 メソッド パス ステータス 応答ミリ秒 customer=ID
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
log="$here/access.log"

echo "--- ステータスごとの件数"
awk '{print $4}' "$log" | sort | uniq -c | sort -rn

echo "--- 500 を返したパスの上位 3 件"
awk '$4 == 500 {print $3}' "$log" | sort | uniq -c | sort -rn | head -n 3

echo "--- パスごとの平均応答ミリ秒"
awk '{sum[$3] += $5; n[$3]++} END {for (p in sum) printf "%s %.1f\n", p, sum[p] / n[p]}' "$log" | sort

echo "--- grep の使い方"
grep -c ' 500 ' "$log"
grep -E 'POST /(cart|checkout) ' "$log" | head -n 2
grep -v ' 200 ' "$log" | wc -l

echo "--- リダイレクト"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
awk '$4 == 500' "$log" > "$work/errors.log"
awk '$4 == 404' "$log" >> "$work/errors.log"
wc -l < "$work/errors.log"
ls /no/such/dir 2> "$work/stderr.txt" || true
cat "$work/stderr.txt"
ls /no/such/dir > /dev/null 2>&1 || echo "終了コード: $?"
