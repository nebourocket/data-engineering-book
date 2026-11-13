#!/usr/bin/env bash
# 長く動く処理の手元での扱い (コマンドの例です。テストでは構文だけ確かめます)。
set -euo pipefail

curl --fail --silent --show-error --location -o rates.json https://api.example.com/rates
tail -f /var/log/neboske/cron.log
nohup ./daily_report.sh access.log reports 2026-11-02 > report.out 2>&1 &
tmux new -s neboske
