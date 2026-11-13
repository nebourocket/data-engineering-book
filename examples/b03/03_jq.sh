#!/usr/bin/env bash
# JSON Lines (1 行 1 レコードの JSON) を jq で読みます。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
events="$here/events.jsonl"

echo "--- 購入したお客さんの ID"
jq -r 'select(.event_type == "purchase") | .customer_id' "$events"

echo "--- イベントの種類ごとの件数"
jq -r '.event_type' "$events" | sort | uniq -c | sort -rn

echo "--- 配信の遅れ (秒) が 10 秒を超えたもの"
jq -c '{event_id, delay: ((.received_at | strptime("%Y-%m-%d %H:%M:%S") | mktime) - (.event_time | strptime("%Y-%m-%d %H:%M:%S") | mktime))} | select(.delay > 10)' "$events"

echo "--- CSV に変える"
jq -r '[.event_id, .customer_id, .event_type] | @csv' "$events" | head -n 3
