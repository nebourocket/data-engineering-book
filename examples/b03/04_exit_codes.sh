#!/usr/bin/env bash
# 終了コードと set -euo pipefail の効き方を確かめます。
here=$(cd "$(dirname "$0")" && pwd)

grep -q ' 200 ' "$here/access.log"
echo "見つかった: $?"
grep -q ' 999 ' "$here/access.log"
echo "見つからなかった: $?"
no_such_command_xyz 2> /dev/null
echo "コマンドが無い: $?"

echo "--- パイプの途中の失敗"
bash -c 'false | cat; echo "pipefail なし: $?"'
bash -c 'set -o pipefail; false | cat; echo "pipefail あり: $?"'

echo "--- set -e と set -u"
bash -c 'set -e; false; echo "ここには来ない"' || echo "set -e で止まった: $?"
bash -c 'set -u; echo "値: ${UNSET_NAME}"' 2> /dev/null || echo "set -u で止まった"
