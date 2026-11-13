#!/usr/bin/env bash
# 環境変数と秘密の扱い。値の例は全部ダミーです。
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

# 変数は export しないと、子プロセスには渡らない
region=tokyo
bash -c 'echo "export なし: [${region:-空}]"'
export region
bash -c 'echo "export あり: [${region:-空}]"'

# 既定値と必須チェック
echo "${BATCH_SIZE:-1000}"
(: "${API_KEY:?API_KEY を設定してください}") || echo "必須の変数が無いので止めた"

# .env ファイルを読み込む (.env は Git に入れない)。source は中身をシェルのコードとして実行するので、
# 値に空白や $ ; を含めるなら引用符が要る。信頼できるファイルだけを読む
umask 077   # これから作るファイルは、持ち主だけが読み書きできる
printf 'API_KEY=dummy-key-0123456789\nBATCH_SIZE=500\n' > .env
stat -c '%a %n' .env
set -a
source .env
set +a
echo "${BATCH_SIZE}"
echo "${API_KEY:0:5}***"   # 秘密はログに全部出さない
