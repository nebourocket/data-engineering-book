#!/usr/bin/env bash
# 前の実行が終わっていないときは、今回の実行をやめる (flock)。
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
lock="$work/job.lock"

# 前回の実行のつもり: ロックを持ったまま 2 秒かかる
( flock -n 9 || exit 1; sleep 2 ) 9> "$lock" &
sleep 0.5

flock -n "$lock" true || echo "前の実行がまだ動いているので、今回はやめた"
wait
flock -n "$lock" true && echo "終わった後は、ロックが取れる"
