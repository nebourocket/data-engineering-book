#!/usr/bin/env bash
# ssh の基本 (コマンドの例です。テストでは構文だけ確かめます)。
set -euo pipefail

# 人が使う鍵はパスフレーズを設定する (夜間に動く鍵は、本文の注意を参照)
ssh-keygen -t ed25519 -C "neboske-batch" -f ~/.ssh/id_ed25519_neboske
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519_neboske
ssh-copy-id -i ~/.ssh/id_ed25519_neboske.pub deploy@batch.example.com
ssh neboske-batch 'df -h /data'
scp neboske-batch:/srv/reports/errors.csv .
ssh -L 15432:localhost:5432 neboske-batch
