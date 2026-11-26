#!/usr/bin/env bash
# 実行権限の確認。
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

printf '#!/usr/bin/env bash\necho hello\n' > hello.sh
stat -c '%A %a' hello.sh
./hello.sh || echo "終了コード: $?"
chmod u+x hello.sh
stat -c '%A %a' hello.sh
./hello.sh
