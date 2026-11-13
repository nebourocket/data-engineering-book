#!/usr/bin/env bash
# ssh の基本 (コマンドの例です。テストでは構文だけ確かめます)。
set -euo pipefail

ssh-keygen -t ed25519 -C "neboske-batch" -f ~/.ssh/id_ed25519_neboske
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519_neboske
ssh neboske-batch 'df -h /data'
scp neboske-batch:/srv/reports/errors.csv .
ssh -L 15432:localhost:5432 neboske-batch
