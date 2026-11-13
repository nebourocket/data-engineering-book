# 第3章 Linux・シェル・Git

## この章でできるようになること

- ファイルとディレクトリをコマンドで扱い、パイプとリダイレクトでコマンドをつなげる。
- `grep`・`sort`・`uniq`・`awk`・`jq` で、ねぼすけ商店のアクセスログを集計する。
- 終了コードと `set -euo pipefail` を使い、失敗したら黙って進まないスクリプトを書く。
- 権限、環境変数、cron、ssh の考え方を説明でき、秘密をリポジトリに入れない運用ができる。
- Git で変更を小さく区切り、ブランチと PR で共有する。衝突の直し方と、秘密を push してしまったときの手順を知っている。

**動かす場所。**この章のコマンドは Linux（GNU 版のコマンド）で動かす前提です。Windows なら WSL か Linux の仮想マシン、Mac なら Docker か Linux のサーバを使ってください。本書のリポジトリの Docker イメージには、必要な道具が入っています（`docker build -t de-book-dev .`）。

**コードの読み方。**本文のブロックは `examples/b03/` の `01_files.sh` や `02_pipes.sh` の一部です。`bash 01_files.sh` のように動かすと、本文の出力例が得られ、`pytest` も同じ出力かを確かめています。エラーメッセージの文言は言語設定（ロケール）で変わります。出力例は `LC_ALL=C`（英語）で取ったものです。

## なぜデータエンジニアはシェルと Git を使うのか

データ基盤の仕事場は、たいていマウスの届かない場所にあります。バッチを動かすサーバには画面がなく、CI（変更のたびに自動でテストを走らせる仕組み）も Docker のコンテナも、入口はコマンドラインです。夜中に動くジョブが失敗した朝、最初にやることは「ログを開いて、何が何件起きたかを数える」ことです。

この章で扱う道具は 5 つです。**シェル**（この本では bash）は、コマンドを起動して結果を受け取るプログラムです。**Linux のコマンド**は小さな部品で、つなげると集計になります。**cron** は決めた時刻にコマンドを動かす仕組み、**ssh** は別の機械に安全につないでコマンドを動かす仕組み、**Git** はファイルの変更履歴を記録して共有する道具です。

## ファイルとディレクトリ

Linux のファイルは、`/` を根にした木のどこかに置かれます。場所の書き方（パス）には 2 種類あります。`/home/deploy/data/raw/access.log` のように根から全部書くのが**絶対パス**、`data/raw/access.log` のように今いる場所（カレントディレクトリ）から書くのが**相対パス**です。`.` は今のディレクトリ、`..` はひとつ上を指します。`pwd` で今いる場所を見て、`cd ディレクトリ` で移ります。

まず、使い捨ての作業ディレクトリを作り、ファイルを置いて、動かしてみます。

```bash
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

mkdir -p data/raw data/clean
cp "$here/access.log" data/raw/2026-11-02.log
find data -type d | sort
```

`mktemp -d` は、他と重ならない名前の一時ディレクトリを作ります。`mkdir -p` は途中のディレクトリもまとめて作り、すでにあってもエラーにしません。何度動かしても同じ状態になります（冪等）。`find data -type d` は `data` の下のディレクトリを全部列挙します。`find` が返す順序は保証されていないので、`sort` で整えます（`ls` は既定で名前順に並べますが、並び方は言語設定に左右されます）。

```text
data
data/clean
data/raw
```

次はファイルの中身を見る道具です。

```bash
wc -l < data/raw/2026-11-02.log
head -n 3 data/raw/2026-11-02.log
tail -n 2 data/raw/2026-11-02.log
```

`wc -l` は行数を数えます。`< ファイル` と書くと、ファイル名が出力に混ざらず数字だけが返ります。`head -n 3` は先頭の 3 行、`tail -n 2` は末尾の 2 行です。巨大なファイルを `cat`（全部を流す）すると端末が固まるので、まず `head` で形を見ます。長いものを読むときは `less`（スペースで進み、`q` で終わる）、書き足されていくログを追うときは `tail -f` が便利です。大きさは `ls -l`（権限・大きさ・名前の一覧）や `du`（ディレクトリの大きさ）、ディスクの空きは `df` で見ます。

```text
60
2026-11-02T09:05:17+09:00 GET /products/12 304 21 customer=22
2026-11-02T09:05:36+09:00 POST /cart 200 16 customer=25
2026-11-02T09:09:34+09:00 GET /products/12 200 45 customer=4
2026-11-02T11:58:04+09:00 GET /products/12 200 22 customer=17
2026-11-02T11:59:16+09:00 GET /products/7 500 19 customer=14
```

名前の変更と削除は次のとおりです。

```bash
mv data/raw/2026-11-02.log data/raw/access-20261102.log
ls data/raw
rm data/raw/access-20261102.log
ls data/raw | wc -l
```

```text
access-20261102.log
0
```

`mv` は移動と名前の変更を兼ねます。`rm` は削除で、ごみ箱がありません。消したファイルは戻りません。`rm -rf "$dir/"*` のように変数を使うときは、`$dir` が空だと `/` 直下の全部が対象になります。`set -u`（後述）は「未設定」しか捕まえず、空文字は通します。`"${dir:?}"` と書くと、空でも未設定でも止まります。変数は `"$変数"` のように二重引用符で囲みます。囲まないと、空白を含むファイル名が複数の引数に割れます。

ワイルドカード（`*` や `?`）は、コマンドではなくシェルが展開します。`grep` の検索パターンの `*` を引用符で囲むのは、このためです。

長い処理を手元で動かすときは、`nohup`（端末を閉じても止めない）や `tmux`（切り離せる端末）を使い、通信が必要なら `curl` を使います。`--fail` を付けると、HTTP のエラーを終了コードに反映します。

```bash
curl --fail --silent --show-error --location -o rates.json https://api.example.com/rates
tail -f /var/log/neboske/cron.log
nohup ./daily_report.sh access.log reports 2026-11-02 > report.out 2>&1 &
tmux new -s neboske
```

ログは圧縮して置かれることが多く、`zcat`・`zgrep` で展開せずに読めます。

```bash
gzip -c "$here/access.log" > access.log.gz
zcat access.log.gz | wc -l
zgrep -c ' 500 ' access.log.gz
ls -l access.log.gz | awk '{print $1, $9}'
du -k "$here/access.log" | awk '{print ($1 > 0) ? "サイズあり" : "空"}'
df -P . | awk 'NR == 2 {print "使用率の列:", $5 ~ /%$/}'
```

```text
60
15
-rw-r--r-- access.log.gz
サイズあり
使用率の列: 1
```

## パイプとリダイレクト

Linux のコマンドは、3 本の通り道を持っています。0 番の**標準入力**、1 番の**標準出力**、2 番の**標準エラー出力**です。ふつうに実行すると、標準入力はキーボード、標準出力と標準エラー出力は画面につながっています。

**パイプ**（`|`）は、左のコマンドの標準出力を、右のコマンドの標準入力につなぎます。**リダイレクト**は、通り道の行き先をファイルに変えます。

{{ table("b03-redirect") }}

結果は次のコマンドへ流し、エラーは人の目に見える場所へ出したいので、出力は 2 本に分かれています。`> out.txt` としても、エラーは画面に出ます。エラーも一緒にファイルへ残したいときは `> out.txt 2>&1` と書きます。`2>&1` は「2 番を、今 1 番がつながっている場所へ向ける」という意味なので、`> out.txt` より後ろに書きます。順序を逆にすると、エラーは画面に出たままになります。

パイプの利点は、途中結果を一時ファイルにしなくてよいことです。コマンド同士が並行して動き、前のコマンドが出した分から次のコマンドが処理を始めます。大きなファイルでも、全体をメモリに載せずに済みます。次の章のジェネレータと同じ考え方です。

## ログを集計する

ねぼすけ商店のウェブサーバが、ある日のアクセスログを残したとします。1 行が 1 リクエストで、空白区切りの 6 項目です。

```text
2026-11-02T09:05:17+09:00 GET /products/12 304 21 customer=22
```

左から、時刻、メソッド、パス、ステータス（200 は成功、404 は無い、500 はサーバ側の失敗）、応答ミリ秒、お客さんの ID です。サンプルは 60 行で、`examples/b03/access.log` にあります。障害のあった日、という設定なので 500 が多めです。

最初の質問は「ステータスごとに何件か」です。

```bash
echo "--- ステータスごとの件数"
awk '{print $4}' "$log" | sort | uniq -c | sort -rn
```

`awk '{print $4}'` は、各行の 4 番目の項目を取り出します。`sort` で同じ値を隣り合わせにし、`uniq -c` で連続する同じ行を数え、最後に `sort -rn` で件数の多い順に並べます。

```text
--- ステータスごとの件数
     32 200
     15 500
      8 304
      5 404
```

`sort | uniq -c | sort -rn` は、出現回数を数える定型句です。ログ、CSV の列、単語など何にでも使えます。`uniq` は**隣り合う**重複しか見ないので、必ず先に `sort` します。これを忘れると、数えた結果が静かにずれます。

次は「500 を返しているのはどのパスか」です。

```bash
echo "--- 500 を返したパスの上位 3 件"
awk '$4 == 500 {print $3}' "$log" | sort | uniq -c | sort -rn | head -n 3
```

`awk` の `$4 == 500` は条件で、真の行だけが `{...}` の処理に進みます。

```text
--- 500 を返したパスの上位 3 件
      5 /checkout
      4 /products/12
      2 /products/7
```

`/checkout`（支払い）が最も多く、売上に直結するので優先して調べる場所です。数字を出すだけで、次の行動が決まります。パスごとの平均は、`awk` の連想配列（キーで値を引く表）を使います。

```bash
echo "--- パスごとの平均応答ミリ秒"
awk '{sum[$3] += $5; n[$3]++} END {for (p in sum) printf "%s %.1f\n", p, sum[p] / n[p]}' "$log" | sort
```

`sum[$3] += $5` は、パスをキーにして応答時間を足し込みます。`END` は最後の行を読み終えた後に 1 度だけ動きます。`awk` の出力順は保証されないので、`sort` で整えます。`awk` の機能は実装（`gawk`・`mawk`）で差があるので、この章は両方で動く範囲にとどめています。

```text
--- パスごとの平均応答ミリ秒
/ 58.8
/cart 53.3
/checkout 30.5
/products/12 37.8
/products/31 34.4
/products/7 26.9
/search 63.2
```

`grep` は行を絞り込みます。

```bash
echo "--- grep の使い方"
grep -c ' 500 ' "$log"
grep -E 'POST /(cart|checkout) ' "$log" | head -n 2
grep -v ' 200 ' "$log" | wc -l
```

`-c` は一致した行数、`-E` は拡張正規表現（`|` や `()` が使える）、`-v` は一致しない行を選びます。

```text
--- grep の使い方
15
2026-11-02T09:05:36+09:00 POST /cart 200 16 customer=25
2026-11-02T09:15:25+09:00 POST /checkout 500 18 customer=9
28
```

最後に、リダイレクトの実例です。

```bash
echo "--- リダイレクト"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
awk '$4 == 500' "$log" > "$work/errors.log"
awk '$4 == 404' "$log" >> "$work/errors.log"
wc -l < "$work/errors.log"
ls /no/such/dir 2> "$work/stderr.txt" || true
cat "$work/stderr.txt"
ls /no/such/dir > /dev/null 2>&1 || echo "終了コード: $?"
```

エラー行を `errors.log` に集め、`ls` の失敗メッセージ（標準エラー出力）を別ファイルに受けています。最後の行は、出力を全部捨てて終了コードだけを使う書き方です。`/dev/null` は何を書いても消える特別なファイルです。

```text
--- リダイレクト
20
ls: cannot access '/no/such/dir': No such file or directory
終了コード: 2
```

### どこまでシェルでやるか

シェルのパイプは、手早く確かめる場面で強い道具です。ただ、毎日動かして結果を残す処理や、型の検査が要る処理を延々とシェルで書くと、保守できなくなります。

{{ table("b03-tool-choice") }}

判断の基準は 2 つです。「他の人（半年後の自分を含む）が読めるか」と「失敗したときに原因を追えるか」。パイプが 4 段を超えたら、Python か SQL に移すことを考えます。

## JSON を jq で読む

API の応答やイベントログは、JSON で届くことが多くなります。1 行に 1 つの JSON を置く形式を **JSON Lines** と呼びます。`jq` は JSON を読み、絞り込み、整形するコマンドです。

```bash
echo "--- 購入したお客さんの ID"
jq -r 'select(.event_type == "purchase") | .customer_id' "$events"

echo "--- イベントの種類ごとの件数"
jq -r '.event_type' "$events" | sort | uniq -c | sort -rn
```

`select(条件)` は条件に合うものだけを通し、`.customer_id` はキーの値を取り出します。`-r` は文字列から引用符を外して出力します。`jq` の式の中でもパイプ（`|`）を使い、左の結果を右に渡します。

```text
--- 購入したお客さんの ID
343
--- イベントの種類ごとの件数
      6 view
      1 purchase
      1 add_to_cart
```

配列を CSV の 1 行にする `@csv` もよく使います。

```bash
echo "--- CSV に変える"
jq -r '[.event_id, .customer_id, .event_type] | @csv' "$events" | head -n 3
```

```text
--- CSV に変える
1340,343,"purchase"
3393,91,"view"
2155,200,"view"
```

`jq` は便利ですが、入れ子が深くなると式が読めなくなります。式が 2 行を超えるなら、Python で `json` を読むほうが後で楽です。

## 終了コードと set -euo pipefail

コマンドは終わるとき、0〜255 の数（**終了コード**）を返します。0 が成功、それ以外は失敗です。直前のコマンドの終了コードは `$?` で読めます。`if` や `&&` や `||` は、この数で動きます。

{{ table("b03-exit-codes") }}

`grep` が何も見つけなかったときの 1 は、エラーではなく「0 件」を意味します。コマンドごとに意味が違うので、迷ったら `man` で確かめます。

```bash
grep -q ' 200 ' "$here/access.log"
echo "見つかった: $?"
grep -q ' 999 ' "$here/access.log"
echo "見つからなかった: $?"
no_such_command_xyz 2> /dev/null
echo "コマンドが無い: $?"
```

```text
見つかった: 0
見つからなかった: 1
コマンドが無い: 127
```

シェルスクリプトは、何も指定しないと、途中のコマンドが失敗しても次の行へ進みます。ファイルのコピーに失敗したのに、空のファイルを集計して「0 件でした」と報告する、という事故はこうして起きます。次の 3 つのオプションを先頭に書いて防ぎます。

- `set -e`: コマンドが失敗したらスクリプトを止める。
- `set -u`: 未定義の変数を使ったらエラーにする（空文字は通る）。
- `set -o pipefail`: パイプの途中のコマンドが失敗したら、全体を失敗にする。

3 つ目が見落とされがちです。パイプの終了コードは、既定では最後のコマンドのものだけです。

```bash
echo "--- パイプの途中の失敗"
bash -c 'false | cat; echo "pipefail なし: $?"'
bash -c 'set -o pipefail; false | cat; echo "pipefail あり: $?"'

echo "--- set -e と set -u"
bash -c 'set -e; false; echo "ここには来ない"' || echo "set -e で止まった: $?"
bash -c 'set -u; echo "値: ${UNSET_NAME}"' 2> /dev/null || echo "set -u で止まった"
```

```text
--- パイプの途中の失敗
pipefail なし: 0
pipefail あり: 1
--- set -e と set -u
set -e で止まった: 1
set -u で止まった
```

`false | cat` は、`pipefail` なしだと成功（0）になります。`pipefail` を付けて初めて、途中の失敗が見えます。

`set -e` には注意点があります。`if` の条件、`&&` や `||` の左側のコマンドなど、結果を見て分岐する場所での失敗は、止まる対象になりません（Bash マニュアルの `set` の項）。万能の保険ではないので、重要な処理の後は明示的に結果を確かめます。

実用的な形を 1 つ示します。指定した日のログから、エラー（500 以上）の集計を書き出す `daily_report.sh` です。

```bash
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
```

ポイントは 4 つあります。

1. `${1:?メッセージ}` は、引数が無いと、メッセージを出して止まります。**処理する日付を引数で受け取る**ので、再実行しても同じ日を処理できます。実行した時刻から「今日」を決めると、遅れて動いたときに別の日を処理してしまいます。
2. 結果は、いきなり本番の名前で書かず、同じディレクトリの一時ファイルに書いて最後に `mv` します。同じファイルシステムの中の `mv` は一瞬で終わるので、読む側が書きかけのファイルを見ることがありません。
3. `mktemp` は持ち主だけが読める権限（0600）でファイルを作り、`mv` しても残ります。読む人がいるなら、`mv` の前に `chmod 644` で権限を広げます。
4. `trap '...' EXIT` は、スクリプトが終わるとき（失敗も含む）に動きます。ただし動くのは、通常の終了とほとんどのシグナルのときで、`SIGKILL` や電源断では動きません。起動時に古い一時ファイルを掃除する備えも考えます。

「書きかけを公開しない」「失敗したら後片付けをして、非 0 で終わる」は、12 章のオーケストレーションでも繰り返し出てきます。

## 権限

Linux のファイルには、持ち主、グループ、その他の 3 者に対して、読む（`r`）・書く（`w`）・実行する（`x`）の許可が付いています。`ls -l` や `stat` で見ると、`-rwxr--r--` のように 10 文字で表示されます。先頭の 1 文字はファイルの種類、続く 3 文字ずつが持ち主・グループ・その他です。

数字でも書けます。`r` を 4、`w` を 2、`x` を 1 として足し、3 者を並べます。`644` は、持ち主が読み書き、他は読むだけ。`600` は、持ち主だけが読み書きできる、という意味です。

```bash
printf '#!/usr/bin/env bash\necho hello\n' > hello.sh
stat -c '%A %a' hello.sh
./hello.sh || echo "終了コード: $?"
chmod u+x hello.sh
stat -c '%A %a' hello.sh
./hello.sh
```

実行権限（`x`）がないスクリプトを動かすと、終了コード 126 で失敗します。

```text
-rw-r--r-- 644
05_permissions.sh: line 10: ./hello.sh: Permission denied
終了コード: 126
-rwxr--r-- 744
hello
```

出力の `05_permissions.sh: line 10:` は、実行したスクリプトの名前と行番号で、`bash` が付けるものです。`chmod u+x` で持ち主に実行権限を足すと動きます。`chmod +x` の忘れは定番の失敗です。

権限は秘密を守る最低限の仕組みでもあります。パスワードや鍵のファイルは `chmod 600` にして、他のユーザーに読ませません。ssh は、鍵の権限が広すぎると使うのを拒みます。

## 環境変数と秘密

**環境変数**は、プロセス（動いているプログラム）に渡す名前付きの値です。接続先やバッチの大きさなど、環境によって変わる設定を、コードの外に出すために使います。

```bash
# 変数は export しないと、子プロセスには渡らない
region=tokyo
bash -c 'echo "export なし: [${region:-空}]"'
export region
bash -c 'echo "export あり: [${region:-空}]"'

# 既定値と必須チェック
echo "${BATCH_SIZE:-1000}"
(: "${API_KEY:?API_KEY を設定してください}") || echo "必須の変数が無いので止めた"
```

`region=tokyo` はシェルの変数で、`export` するまで子プロセスには渡りません。`${変数:-既定値}` は未設定なら既定値を使い、`${変数:?メッセージ}` は未設定なら止まります。

```text
export なし: [空]
export あり: [tokyo]
1000
05_env_secrets.sh: line 16: API_KEY: API_KEY を設定してください
必須の変数が無いので止めた
```

環境ごとに変わる値は、`.env` のようなファイルに書いて読み込む運用がよく使われます。

```bash
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
```

`umask 077` は、これから作るファイルの権限から、グループとその他の権限を引きます（`.env` が 600 になります）。`set -a` の間に読み込んだ変数は自動的に `export` されます。注意が 1 つあります。`source` は `.env` の中身をシェルのコードとして**実行**します。値に空白や `$`・`;` を含めるなら引用符が要り、他人が書き換えられるファイルを読むと、任意のコマンドが動きます。

```text
600 .env
500
dummy***
```

秘密（パスワード、API キー、トークン）の扱いは、次の 4 つの決まりで十分です。

1. **コードにも Git にも書かない。**`.env` は `.gitignore` に入れます。リポジトリには、値を空にした `.env.example` だけを置きます。
2. **コマンドの引数に書かない。**`ps` で他のユーザーにも見えます。環境変数かファイルで渡します。
3. **ログに出さない。**デバッグで `print(os.environ)` を書くと、鍵が全部ログに載ります。出すなら先頭の数文字だけにします。
4. **漏れたら失効させる。**後述のとおり、Git から消しても履歴は残るので、鍵そのものを無効にして作り直すのが確実な対処です。

設定を環境変数で渡す考え方は、「The Twelve-Factor App」の設定の項に由来します。4 章でも、この方針で Python の設定を作ります。

## cron とタイムゾーン

cron は、時刻の書かれた表（crontab）を 1 分ごとに見て、合うコマンドを動かします。時刻は 5 つの欄、分・時・日・月・曜日で書きます。

```ini
# 分 時 日 月 曜日 コマンド
SHELL=/bin/bash
MAILTO=""
15 3 * * * flock -n /var/lock/neboske-daily.lock /opt/neboske/bin/daily_report.sh /var/log/neboske/access.log /srv/reports $(date +\%F -d yesterday) >> /var/log/neboske/cron.log 2>&1
```

`15 3 * * *` は「毎日 3 時 15 分」です。`*` は「すべて」を意味します。コマンドの末尾の `>> cron.log 2>&1` で、標準出力と標準エラー出力を、ログファイルの末尾に足しています。これを書かないと、出力は捨てられるか、メールとして送られます（`MAILTO`）。**cron は終了コードを見ません。**失敗に気づくには、ログを監視するか、失敗時に通知するラッパーが要ります（終了コードを見て再試行や通知をするのは、12 章のオーケストレーターの役目です）。

cron には、はまりどころがいくつかあります（Debian の `crontab(5)` と `cron(8)` による）。

- 既定のシェルは `/bin/sh` で、cron が用意する環境変数は `SHELL`・`LOGNAME`・`HOME` くらいです。自分のシェルの設定（`.bashrc`）は読まれません。上の例は `SHELL=/bin/bash` を指定しています。`PATH` の通っていないコマンドが「見つからない」（127）になることもあるので、スクリプトは絶対パスで書きます。
- コマンドの中の `%` は、改行として扱われます。そのため、`date +\%F` のように `\` で守ります。
- コメントは、コマンドと同じ行に書けません。
- Debian の cron が扱えるタイムゾーンは 1 つだけで、その機械の設定（`/etc/timezone`）に従います。cronie（`crontab(5)` に `CRON_TZ` の説明があります）など別の実装は変数で指定できますが、実装によって違うので、使う環境の `man crontab` で確かめます。systemd のタイマーなら、`OnCalendar=` にタイムゾーンを書けます。
- 夏時間の切り替えのように時計が 3 時間未満ずれたとき、時刻を決め打ちしたジョブは、進んで飛ばされた時刻の分が切り替えの直後に動き、戻って繰り返された時刻の分は再実行されません（`cron(8)`）。夏時間のある地域では注意します。

**重なり実行。**前回の処理が長引いて、次の時刻が来てしまうことがあります。同じ処理が同時に 2 つ動くと、同じファイルに書いて壊しかねません。`flock` は、ファイルを錠前にして、取れなければ（`-n`）諦めるコマンドです。上の crontab の行はこれを使っています。

```bash
# 前回の実行のつもり: ロックを持ったまま 2 秒かかる
( flock -n 9 || exit 1; sleep 2 ) 9> "$lock" &
sleep 0.5

flock -n "$lock" true || echo "前の実行がまだ動いているので、今回はやめた"
wait
flock -n "$lock" true && echo "終わった後は、ロックが取れる"
```

```text
前の実行がまだ動いているので、今回はやめた
終わった後は、ロックが取れる
```

次に、時刻の問題です。

```bash
# 日本時間の 2026-11-02 03:15 は、UTC では前の日
TZ=Asia/Tokyo date -d '2026-11-02 03:15' '+JST %F %T %z'
date -u -d '2026-11-02 03:15 +0900' '+UTC %F %T'

# ログの時刻は +09:00 付き。UTC に直して日付で分ける
date -u -d '2026-11-02T00:30:00+09:00' '+%F'
```

```text
JST 2026-11-02 03:15:00 +0900
UTC 2026-11-01 18:15:00
2026-11-01
```

日本時間の 3 時 15 分は、UTC では前の日の 18 時 15 分です。サーバが UTC で動いていると、「日本の 1 日分」を取り込むつもりのバッチが、日付の境目で 1 日ずれます。ログの時刻が `+09:00` 付きのとき、同じ瞬間が UTC では前日の日付になるのも、この例のとおりです。crontab の `$(date +\%F -d yesterday)` は、「その機械の時計での昨日」を渡します。機械のタイムゾーンが想定と違えば、日付もずれます。

対策は次のとおりです。

- 保存する時刻は、タイムゾーン付きで UTC にそろえる。表示のときだけ日本時間にする。Airflow（12 章）も、内部では UTC で時刻を持つのが既定です。
- 「何日分を処理するか」は、引数で明示する（上の `daily_report.sh`）。再実行しても同じ結果になります。
- サーバのタイムゾーンを、README に書く。

## ssh

ssh は、別の機械に暗号化された通信でつなぎます。パスワードの代わりに、**鍵のペア**を使う方法が一般的です。ペアのうち、秘密鍵は手元に置き、公開鍵だけをつなぎ先に登録します。秘密鍵を持っている人だけが入れます。秘密鍵は誰にも渡さず、Git にも入れません。鍵の作成時に聞かれるパスフレーズは必ず設定します。鍵のファイルが盗まれても、そのままでは使われません。

```bash
# パスフレーズを聞かれたら、必ず設定する
ssh-keygen -t ed25519 -C "neboske-batch" -f ~/.ssh/id_ed25519_neboske
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519_neboske
ssh-copy-id -i ~/.ssh/id_ed25519_neboske.pub neboske-batch
```

`ed25519` は現在よく使われる鍵の種類です。`ssh-copy-id` は、公開鍵をつなぎ先の `~/.ssh/authorized_keys`（入ってよい鍵の一覧）に追記します。初めてつなぐ機械では、「この機械の指紋を信用するか」と聞かれます。管理者から聞いた指紋と合うことを確かめて `yes` と答えると、`~/.ssh/known_hosts` に記録され、次からは機械が入れ替わっていないかを自動で確かめます。

```bash
ssh neboske-batch 'df -h /data'
scp neboske-batch:/srv/reports/errors.csv .
ssh -L 15432:localhost:5432 neboske-batch
```

`ssh 別名 'コマンド'` は、つないだ先でそのコマンドだけを動かします。`scp` はファイルのコピーです。`-L` は**ポートフォワード**です。ポートは、1 台の機械の中でサービスを見分ける番号で（PostgreSQL は既定で 5432）、手元の 15432 番を、つなぎ先から見た `localhost:5432` につなぎます。外から直接つなげない PostgreSQL に、手元の道具で入るときに使います。

毎回オプションを打つのは大変なので、`~/.ssh/config` に別名を書きます。

```ini
Host neboske-batch
    HostName batch.example.com
    User deploy
    IdentityFile ~/.ssh/id_ed25519_neboske
    IdentitiesOnly yes
```

`IdentitiesOnly yes` は、指定した鍵だけを試す設定です。個々の設定の意味は、`ssh_config(5)` で確かめられます。

## Git

### 仕組み: 3 つの場所

Git で混乱しやすいのは、変更が 3 つの場所を行き来することです。

{{ table("b03-git-areas") }}

`git add` は「この変更を次のコミットに入れる」という予約、`git commit` は予約した内容の記録です。履歴に入るのはステージした分だけなので、`git status` で何が入るかを確かめてからコミットします。

### コミットの粒度

コミットは、**1 つの目的**に対して 1 つ作ります。「注文の検証を足した」と「ログの文言を直した」は、別のコミットです。粒度が細かいと、問題が起きたときにそのコミットだけを `git revert` で取り消せ、レビューする人が意図を 1 つずつ追えます。メッセージは、何を変えたかが 1 行で分かるようにします。この本のリポジトリでは `feat:`（機能）、`fix:`（修正）、`docs:`（文書）のように種類を頭に付けています。これは慣習で、チームのルールに合わせます。目的が混ざったときは、`git add -p` で変更を部分ごとに選べます。

### ブランチとマージ

ブランチは、コミットに付ける動かせる名前です。`main` から作業用のブランチを切って変更し、できたら `main` に取り込みます。`main` は常に動く状態に保つ約束です。

```bash
git init -q -b main shop
cd shop
git config user.name "Nebou Rocket"
git config user.email "rocket@example.com"

# 1 コミット = 1 つの目的
printf 'import csv\n' > etl.py
git add etl.py
git commit -q -m "feat: ETL の雛形を追加"

# ブランチを切って作業し、main に戻して取り込む
git switch -q -c feat/validate-orders
printf 'def validate(row):\n    return row\n' >> etl.py
git commit -q -am "feat: 注文行の検証を追加"
git switch -q main
git merge -q --no-ff feat/validate-orders -m "Merge branch 'feat/validate-orders'"
git log --graph --format='%s'
```

`git init -b main` で `main` ブランチを持つ新しいリポジトリを作り、`git switch -c` でブランチを作って移ります。`git merge --no-ff` は、取り込みの記録（マージコミット）を必ず残します。`git log --graph` で、枝分かれと合流が見えます。

```text
*   Merge branch 'feat/validate-orders'
|\  
| * feat: 注文行の検証を追加
|/  
* feat: ETL の雛形を追加
```

ブランチの名前は、`feat/validate-orders` のように「種類/内容」にそろえると、一覧が読みやすくなります。

### 共有: clone・pull・push と衝突

リモート（GitHub など）にあるリポジトリは、`git clone` で手元に写します。以後は、`git pull` で最新を受け取り、`git push` で自分のコミットを送ります。ここで、2 人が同じ行を別々に変えると、**衝突**（コンフリクト）が起きます。次の例は、リモート代わりの bare リポジトリを手元に作り、2 人分の作業場所（alice と bob）で再現します。

```bash
# alice が最初のコミットを push し、bob が受け取る
printf 'batch_size = 100\n' > alice/etl.py
git -C alice add etl.py
git -C alice commit -q -m "feat: ETL の雛形を追加"
git -C alice push -q -u origin main 2> /dev/null
git -C bob pull -q origin main
cat bob/etl.py
```

```text
batch_size = 100
```

```bash
# 2 人が同じ行を別々に変える。先に alice が push する
printf 'batch_size = 500\n' > alice/etl.py
git -C alice commit -q -am "fix: バッチを 500 に"
git -C alice push -q
printf 'batch_size = 1000\n' > bob/etl.py
git -C bob commit -q -am "fix: バッチを 1000 に"
```

bob の手元には、alice が先に push した変更が入っていません。作業中の変更は、`git stash` で一時的に避けておけます。

```bash
# bob の作業中の変更は、stash で一時的に避けておける
printf 'memo\n' > bob/notes.txt
git -C bob add notes.txt
git -C bob stash -q
git -C bob stash list | wc -l
```

```text
1
```

bob が `git pull --rebase` で取り込むと、同じ行を別々に変えているので、衝突して止まります。

```bash
# bob が rebase で取り込むと、衝突して止まる
git -C bob pull --rebase -q origin main > /dev/null 2>&1 || true
git -C bob status --short
# 衝突を直す: どちらの値にするかを決めて書き、add して続ける
printf 'batch_size = 1000\n' > bob/etl.py
git -C bob add etl.py
GIT_EDITOR=true git -C bob rebase --continue > /dev/null 2>&1 || true
git -C bob log --format='%s'
git -C bob stash pop -q
git -C bob status --short
```

```text
UU etl.py
fix: バッチを 1000 に
fix: バッチを 500 に
feat: ETL の雛形を追加
A  notes.txt
```

`UU etl.py` は「両方が変更した」の印です。ファイルに `<<<<<<<` `=======` `>>>>>>>` の印が入るので、残す内容に直して印を消し、`git add` してから `git rebase --continue` で続けます。やめたいときは `git rebase --abort` です。直した後、`git log` で bob のコミットが alice の後ろに付き替わったことが確認できます。`git stash pop` で、避けておいた変更も戻りました。

**merge と rebase の使い分け。**`merge` は合流の記録を残し、履歴は事実のとおりです。`rebase` は自分のコミットを最新の土台の上に付け替えるので、履歴が一直線になり読みやすい一方、コミットが作り直されます。目安は、**まだ他の人に渡していない自分のブランチは rebase してよい。共有したブランチは rebase しない**です。

### PR とレビュー

チームでは、ブランチを直接 `main` に取り込まず、**プルリクエスト（PR）**を出します。PR は、GitHub などの上で「このブランチを `main` に取り込んでよいか」を相談する場です。GitHub につなぐには認証が要ります。`gh auth login` で GitHub CLI にログインするか、SSH の鍵を GitHub に登録して `git@github.com:...` の URL を使うか、トークンを使います。

```bash
gh auth login
ssh -T git@github.com
git clone git@github.com:neboske/etl.git
```

```bash
git switch -c feat/orders-etl origin/main
git add etl.py tests/test_etl.py
git commit -m "feat: 注文 CSV を検証して Parquet に書く"
git push -u origin feat/orders-etl
gh pr create --fill
git fetch origin
git rebase origin/main
git push --force-with-lease
```

`git push -u` は、ブランチをリモートに送り、以後の `push` の送り先を覚えさせます。`gh pr create` は PR を作ります。`git rebase origin/main` の後は履歴が書き換わるので、`push` は `--force-with-lease` を使います。これは、自分が最後に見た状態から他の人が変えていないときだけ、上書きを許す安全版です。ただし、直前の `git fetch` でリモートの追跡ブランチが更新されると、保護は効かなくなります。fetch の後に使うときは、確認した SHA を明示します。

```bash
# fetch の後に使うときは、確認済みの SHA を明示する
git push --force-with-lease=feat/orders-etl:0123abc
```

`main` への強制 push は、チームの決まりとして禁止します。

レビューは、バグを探す場であると同時に、知識を共有する場です。データの仕事では、次の点を見てもらいます。

- 同じ処理を 2 回動かしても、結果が変わらないか（冪等）。
- 元データの欠損、重複、遅れを考えているか。
- 秘密や個人情報が、コードやログに入っていないか。
- テストが付いているか。

レビューをお願いする側は、PR を小さくします。何のための変更かを、PR の説明に書きます。

### .gitignore

`.gitignore` に書いたパターンのファイルは、`git add` の対象になりません。

```bash
# .gitignore に書いたファイルは add されない
printf '.env\ndata/\n__pycache__/\n' > .gitignore
printf 'API_KEY=dummy-key-0123456789\n' > .env
git add .
git status --short
git commit -q -m "chore: .gitignore を追加"
```

```text
A  .gitignore
```

`.env` が `git status` に出てきません。`data/` や `__pycache__/` のように、再生成できるものも書いておきます。`.gitignore` は、**まだ Git が追跡していないファイル**にしか効きません。すでにコミットしたファイルは、書いても追跡が続きます。

```bash
# 差分を見て、変更を取り消す
printf 'print("debug")\n' >> etl.py
git diff --stat
git restore etl.py
git status --short | wc -l
```

`git diff` で作業ツリーの変更を確かめ、`git restore` で戻しています。`git restore` は既定ではステージ（インデックス）の内容から作業ツリーを戻すので、`git add` 済みの変更は残ります。最後のコミットの状態まで戻すには、`git restore --source=HEAD --staged --worktree ファイル` と書きます。どちらも未コミットの変更を捨てるので、戻す前に `diff` で中身を見ます。

```text
 etl.py | 1 +
 1 file changed, 1 insertion(+)
0
```

### 秘密をコミットしてしまったとき

誰でも一度は、`.env` や鍵を `git add` してしまいます。後から消しても、履歴には残ります。

```bash
printf 'API_KEY=dummy-key-0123456789\n' > .env
git add .env
git commit -q -m "add env"

# 気づいて消しても、過去のコミットには鍵が残っている
git rm -q --cached .env
echo '.env' > .gitignore
git add .gitignore
git commit -q -m "stop tracking .env"
git log --oneline | wc -l
git show HEAD~1:.env
git log --all --format='%s' -S'dummy-key-0123456789'
```

```text
2
API_KEY=dummy-key-0123456789
stop tracking .env
add env
```

`.env` を追跡から外した後でも、1 つ前のコミットを指定すれば鍵がそのまま読めます。`-S` は、その文字列が増減したコミットを探すオプションです。

手順は、順番が大事です。

1. **鍵を失効させる。**これが最優先です。公開リポジトリなら、push した時点で第三者に読まれたものとして扱います。非公開でも、クローン（手元に写したコピー）を持つ全員に渡ったとみなします。管理画面で無効にし、新しい鍵を発行します。
2. 新しい鍵は、コードの外（環境変数や、秘密を扱う専用の仕組み）で渡す。
3. まだマージされていないブランチなら、そのブランチを消すか、履歴を書き換えて秘密を取り除き、**自分のブランチだけ**を強制 push する。履歴を書き換えるには `git filter-repo` などを使います。`git filter-branch` のドキュメントは、危険な点を挙げて `git filter-repo` を勧めています。`main` に入ってしまったときは、全員のクローンに影響するので、事前にチームに知らせます。
4. GitHub の場合は、公式ドキュメント「Removing sensitive data from a repository」の手順を確認する。

事前の予防もできます。GitHub の**プッシュ保護**（secret scanning の機能）は、秘密に似た文字列を含む push を受け付けません。書き込み権限のある人は、理由を付けて回避できます。公開リポジトリでは、ユーザー単位の保護が既定で有効です。非公開リポジトリでリポジトリ単位に使うには、有料の GitHub Secret Protection が必要です（2026年11月時点。契約や機能は変わるので、公式ドキュメントで確かめてください）。

## よくある失敗

- **`uniq` の前に `sort` し忘れる。**数えた結果が静かにずれます。
- **`set -e` だけで安心する。**`pipefail` と `-u` も付けます。`if` や `||` の中では効かないことも覚えておきます。
- **cron で動かすと「コマンドが無い」。**自分のシェルと環境が違います。絶対パスで書き、出力をログに残します。
- **日付がずれる。**サーバが UTC で動いていることに気づかない。時刻は UTC で保存し、処理する日付は引数で渡します。
- **秘密を消して終わりにする。**履歴に残ります。まず失効させます。

## まとめ

- コマンドは標準入力・標準出力・標準エラー出力を持ち、パイプとリダイレクトで小さな部品をつなげる。
- スクリプトの先頭には `set -euo pipefail`。結果は一時ファイルに書いて最後に `mv`、日付は引数で渡す。
- 秘密はコードの外に置き、権限は最小に。cron は終了コードを見ず、環境が小さく、重なり実行に備える。時刻は UTC で持つ。
- Git は目的ごとに小さくコミットし、ブランチと PR で共有する。衝突は rebase で直し、秘密を入れたら、先に失効させる。

## 練習問題

問1. `access.log` から、`/products/` で始まるパスへのリクエストだけを取り出し、パスごとの件数を多い順に表示するパイプラインを書いてください。

??? note "解答例"
    ```bash
    awk '$3 ~ /^\/products\// {print $3}' access.log | sort | uniq -c | sort -rn
    ```
    結果は次のとおりです。

    ```text
         20 /products/12
          9 /products/7
          5 /products/31
    ```
    `~` は正規表現に一致するかの判定です。`grep` で先に絞っても構いません。結果が空になる場合は、パスの書き方（`/` の位置）を `head` で確かめます。

問2. 次のスクリプトは、`sort` が失敗しても「完了」と表示し、終了コード 0 で終わります。先頭に何を足せば、失敗で止まるようになりますか。また、その理由を説明してください。

```text
cat input.csv | sort | uniq > result.csv
echo "完了"
```

??? note "解答例"
    `set -euo pipefail` を先頭に足します。パイプの終了コードは、既定では最後のコマンド（`uniq`）のものだけで、`sort` が失敗しても 0 になります。`pipefail` を付けると、途中の失敗が全体の失敗になり、`set -e` がそこでスクリプトを止めます。さらに、`result.csv` は書きかけのまま残るので、`daily_report.sh` のように、一時ファイルに書いて最後に `mv` する形にするとよいです。

問3. 毎日 2 時（UTC）に動くバッチがあります。日本時間の「前日 1 日分」のログを処理したいとき、何に気をつけて設計しますか。3 点挙げてください。

??? note "解答例"
    (1) 例として、2026-11-03 02:00 UTC の実行は、日本時間では 11 時です。ここで処理するのが日本時間の 11 月 2 日分なら、UTC に直すと 2026-11-01 15:00 から 2026-11-02 15:00 までです。境目は、実行時の「今日」ではなく、引数で渡した日付から計算します。(2) ログの時刻は、`+09:00` のようにタイムゾーン付きで読み、UTC か日本時間のどちらかにそろえてから日付で分けます。(3) 再実行しても同じ結果になるよう、出力は日付ごとのファイルに上書きし、追記にしません。サーバのタイムゾーンは README に書きます。

問4. 同僚が誤って `.env`（API キー入り）を含むコミットを、非公開リポジトリのブランチに push しました。まだマージされていません。取るべき手順を順番に書いてください。

??? note "解答例"
    (1) API キーを失効させ、新しいキーを発行する。ブランチを消しても、クローンや PR の記録に残るためです。(2) そのブランチを消すか、`git filter-repo` などで履歴から `.env` を取り除き、そのブランチだけを強制 push する。`main` には触れません。(3) `.env` を `.gitignore` に追加し、追跡から外す（`git rm --cached .env`）。(4) 新しいキーは、環境変数など、コードの外で渡す。(5) 再発防止として、プッシュ保護の有効化や、`.env.example` を置く運用を検討する。

## 参考文献

- GNU Coreutils Manual: <https://www.gnu.org/software/coreutils/manual/coreutils.html>（`sort`・`uniq`・`wc`・`head`・`tail`・`date`・`mktemp`・`chmod`・`stat`）
- Bash Reference Manual: <https://www.gnu.org/software/bash/manual/bash.html>（リダイレクト、`set` の組み込みコマンド、終了ステータス、パラメータ展開）
- The GNU Awk User's Guide: <https://www.gnu.org/software/gawk/manual/gawk.html>
- jq Manual: <https://jqlang.org/manual/>
- Debian `crontab(5)`: <https://manpages.debian.org/bookworm/cron/crontab.5.en.html> ／ `cron(8)`: <https://manpages.debian.org/bookworm/cron/cron.8.en.html>
- cronie 版 `crontab(5)`: <https://man7.org/linux/man-pages/man5/crontab.5.html> ／ systemd.time: <https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html>
- OpenSSH `ssh_config(5)`: <https://man.openbsd.org/ssh_config>
- Apache Airflow ドキュメント「Time zones」: <https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/timezone.html>
- The Twelve-Factor App「III. 設定」: <https://12factor.net/ja/config>
- Git ドキュメント: <https://git-scm.com/docs>（`git-commit`・`git-switch`・`git-merge`・`git-restore`・`git-push`・`gitignore`・`git-filter-branch`）
- Pro Git（日本語版）: <https://git-scm.com/book/ja/v2>
- GitHub Docs「Removing sensitive data from a repository」: <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository>
- GitHub Docs「About push protection」: <https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection>
- git-filter-repo: <https://github.com/newren/git-filter-repo>
- たけぞう『Gitコマンド100本ノック』（3 つの場所、ブランチ、取り消し、リモートの各章）

!!! tip "さらに深く"
    応用編 第9章「ガバナンス・セキュリティ・個人情報」では、秘密と個人情報の管理を組織の仕組みとして扱います。
