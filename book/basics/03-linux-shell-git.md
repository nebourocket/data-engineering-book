# 第3章 Linux・シェル・Git

## この章でできるようになること

- ファイルとディレクトリをコマンドで扱い、パイプとリダイレクトでコマンドをつなげる。
- `grep`・`sort`・`uniq`・`awk`・`jq` で、ねぼすけ商店のアクセスログを集計する。
- 終了コードと `set -euo pipefail` を使い、失敗したら黙って進まないスクリプトを書く。
- 権限、環境変数、cron、ssh の考え方を説明でき、秘密をリポジトリに入れない運用ができる。
- Git で変更を小さく区切り、ブランチと PR で変更を共有する。秘密を push してしまったときの手順を知っている。

この章のコードは `examples/b03/` にあり、`pytest` で実際に動かしています。本文の出力例は、そのとき得られた結果を写したものです。

## なぜデータエンジニアはシェルと Git を使うのか

データ基盤の仕事場は、たいていマウスの届かない場所にあります。バッチを動かすサーバには画面がなく、CI（変更のたびに自動でテストを走らせる仕組み）も、Docker のコンテナも、入口はコマンドラインです。夜中に動くジョブが失敗した朝、最初にやることは「ログを開いて、何が何件起きたかを数える」ことです。

この章で扱う道具は 5 つです。**シェル**（この本では bash）はコマンドを起動して結果を受け取るプログラム、**cron** は決めた時刻にコマンドを動かす仕組み、**ssh** は別の機械に安全につないでコマンドを動かす仕組み、**Git** はファイルの変更履歴を記録して共有する道具です。Linux のコマンドは小さな部品で、1 つが 1 つの仕事しかしませんが、つなげると集計になります。流行のツールが入れ替わっても、その中身はたいていこれらの組み合わせです。

## ファイルとディレクトリ

Linux のファイルは、`/` を根にした木のどこかに置かれます。場所の書き方（パス）には 2 種類あります。`/home/deploy/data/raw/access.log` のように根から全部書くのが**絶対パス**、`data/raw/access.log` のように今いる場所（カレントディレクトリ）から書くのが**相対パス**です。`.` は今のディレクトリ、`..` はひとつ上を指します。

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

`mktemp -d` は、他と重ならない名前の一時ディレクトリを作ります。`mkdir -p` は途中のディレクトリもまとめて作り、すでにあってもエラーにしません。何度動かしても同じ状態になります（冪等）。`find data -type d` は `data` の下のディレクトリを全部列挙し、`sort` で並び順をそろえています。`find` や `ls` の順序は保証されていないので、順序に意味を持たせたいときは自分で `sort` します。

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

`wc -l` は行数を数えます。`< ファイル` と書くと、ファイル名が出力に混ざらず数字だけが返るので、変数に入れるときに便利です。`head -n 3` は先頭の 3 行、`tail -n 2` は末尾の 2 行です。巨大なファイルを `cat` で全部流すと端末が固まるので、まず `head` で形を見る癖をつけます。

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

`mv` は移動と名前の変更を兼ねます。`rm` は削除で、ごみ箱がありません。消したファイルは戻りません。`rm -rf` の `-r` は中身ごと、`-f` は確認なしです。
変数を使う `rm -rf "$dir/"` は、`$dir` が空だと `/` を消しに行く事故につながるので、後で出てくる `set -u` を必ず付けます。変数は `"$変数"` のように二重引用符で囲みます。囲まないと、空白を含むファイル名が複数の引数に割れます。

ワイルドカード（`*` や `?`）は、コマンドではなくシェルが展開します。`ls data/raw/*.log` は、シェルがファイル名の一覧に置き換えてから `ls` を呼びます。この仕組みを知っていると、`grep` の検索パターンの `*` を引用符で囲む理由が分かります。囲まないと、シェルが先に展開してしまうからです。

## パイプとリダイレクト

Linux のコマンドは、3 本の通り道を持っています。0 番の**標準入力**、1 番の**標準出力**、2 番の**標準エラー出力**です。ふつうに実行すると、標準入力はキーボード、標準出力と標準エラー出力は画面につながっています。

**パイプ**（`|`）は、左のコマンドの標準出力を、右のコマンドの標準入力につなぎます。**リダイレクト**は、通り道の行き先をファイルに変えます。

{{ table("b03-redirect") }}

標準出力と標準エラー出力を分ける設計には理由があります。結果は次のコマンドへ流し、エラーは人の目に見える場所へ出したいからです。`> out.txt` としても、エラーは画面に出ます。エラーも一緒にファイルへ残したいときは `> out.txt 2>&1` と書きます。`2>&1` は「2 番を、今 1 番がつながっている場所へ向ける」という意味なので、`> out.txt` より後ろに書きます。順序を逆にすると、エラーは画面に出たままになります。

パイプの利点は、途中結果を一時ファイルにしなくてよいことです。コマンド同士が並行して動き、前のコマンドが出した分から次のコマンドが処理を始めます。大きなファイルでも、全体をメモリに載せずに済みます。これは次の章で扱うジェネレータと同じ考え方です。

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

`sort | uniq -c | sort -rn` は、出現回数を数える定型句です。覚えておくと、ログ、CSV の列、単語など何にでも使えます。`uniq` は**隣り合う**重複しか見ないので、必ず先に `sort` します。これを忘れると、数えた結果が静かにずれます。

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

`/checkout`（支払い）が最も多く、売上に直結するので優先して調べるべき場所です。数字を出すだけで、次の行動が決まります。

パスごとの平均を出すには、`awk` の連想配列を使います。

```bash
echo "--- パスごとの平均応答ミリ秒"
awk '{sum[$3] += $5; n[$3]++} END {for (p in sum) printf "%s %.1f\n", p, sum[p] / n[p]}' "$log" | sort
```

`sum[$3] += $5` は、パスをキーにして応答時間を足し込みます。`END` は最後の行を読み終えた後に 1 度だけ動きます。`awk` の出力順は保証されないので、`sort` で整えます。

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

`awk` の細かい機能は実装によって違い、GNU の `gawk` と、Debian の軽量な `mawk` では差があります。この章の例は両方で動く範囲に絞っています。実装の差に頼る書き方は、別のマシンで動かしたときに壊れます。

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

シェルのパイプは、手早く確かめる場面で強い道具です。ただ、毎日動かして結果を残す処理や、型の検査が要る処理を延々とシェルで書くと、保守できなくなります。目安を表にまとめます。

{{ table("b03-tool-choice") }}

判断の基準は 2 つです。「他の人（半年後の自分を含む）が読めるか」と「失敗したときに原因を追えるか」。パイプが 4 段を超えたら、一度立ち止まって Python か SQL に移すことを考えます。

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

時刻の計算や、CSV への変換もできます。

```bash
echo "--- 配信の遅れ (秒) が 10 秒を超えたもの"
jq -c '{event_id, delay: ((.received_at | strptime("%Y-%m-%d %H:%M:%S") | mktime) - (.event_time | strptime("%Y-%m-%d %H:%M:%S") | mktime))} | select(.delay > 10)' "$events"

echo "--- CSV に変える"
jq -r '[.event_id, .customer_id, .event_type] | @csv' "$events" | head -n 3
```

`strptime` で文字列を時刻に分解し、`mktime` で秒に変えて引き算しています。`@csv` は配列を CSV の 1 行にします。

```text
--- 配信の遅れ (秒) が 10 秒を超えたもの
{"event_id":1340,"delay":15}
{"event_id":2155,"delay":29}
{"event_id":3742,"delay":11}
{"event_id":1996,"delay":25}
{"event_id":1549,"delay":15}
--- CSV に変える
1340,343,"purchase"
3393,91,"view"
2155,200,"view"
```

`jq` はたいへん便利ですが、入れ子が深くなると式が読めなくなります。式が 2 行を超えるなら、Python で `json` を読むほうが後で楽です。

## 終了コードと set -euo pipefail

コマンドは終わるとき、0〜255 の数（**終了コード**）を返します。0 が成功、それ以外は失敗です。直前のコマンドの終了コードは `$?` で読めます。`if` や `&&` や `||` は、この数で動きます。

{{ table("b03-exit-codes") }}

`grep` が何も見つけなかったときの 1 は、エラーではなく「0 件」を意味します。コマンドごとに終了コードの意味が違うので、迷ったら `man` で確かめます。

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
- `set -u`: 未定義の変数を使ったらエラーにする。
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

実用的な形を 1 つ示します。ログから日次のエラー集計を書き出す `daily_report.sh` です。

```bash
set -euo pipefail

log="${1:?使い方: daily_report.sh ログのパス 出力ディレクトリ}"
out_dir="${2:?使い方: daily_report.sh ログのパス 出力ディレクトリ}"

mkdir -p "$out_dir"
tmp=$(mktemp "$out_dir/.report.XXXXXX")
trap 'rm -f "$tmp"' EXIT

# 途中で失敗しても、書きかけのファイルを本番の名前では残さない
echo "path,errors" > "$tmp"
awk '$4 >= 500 {print $3}' "$log" | sort | uniq -c | awk '{print $2 "," $1}' >> "$tmp"
mv "$tmp" "$out_dir/errors.csv"
echo "wrote $out_dir/errors.csv"
```

ポイントは 3 つあります。

1. `${1:?メッセージ}` は、引数が無いと、メッセージを出して止まります。引数の取り忘れが、空文字のまま進むのを防ぎます。
2. 結果は、いきなり本番の名前で書かず、同じディレクトリの一時ファイルに書いて最後に `mv` します。同じファイルシステムの中の `mv` は一瞬で終わるので、読む側が書きかけのファイルを見ることがありません。
3. `trap '...' EXIT` は、スクリプトが終わるとき（失敗も含む）に必ず動きます。失敗した後に一時ファイルが残りません。

この 3 点は、データパイプラインの設計でそのまま使えます。「書きかけを公開しない」「失敗したら後片付けをして、非 0 で終わる」は、12 章のオーケストレーションでも繰り返し出てきます。

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

`chmod u+x` で持ち主に実行権限を足すと動きます。シェルスクリプトは `chmod +x` を忘れる、が定番の失敗です。

権限は秘密を守る最低限の仕組みでもあります。パスワードや鍵のファイルは `chmod 600` にして、他のユーザーに読ませません。ssh は、鍵の権限が広すぎると使うのを拒みます。

## 環境変数と秘密

**環境変数**は、プロセスに渡す名前付きの値です。接続先やバッチの大きさなど、環境によって変わる設定を、コードの外に出すために使います。

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
# .env ファイルを読み込む (.env は Git に入れない)
printf 'API_KEY=dummy-key-0123456789\nBATCH_SIZE=500\n' > .env
chmod 600 .env
stat -c '%a %n' .env
set -a
source .env
set +a
echo "${BATCH_SIZE}"
echo "${API_KEY:0:5}***"   # 秘密はログに全部出さない
```

`set -a` の間に読み込んだ変数は、自動的に `export` されます。

```text
600 .env
500
dummy***
```

秘密（パスワード、API キー、トークン）の扱いは、次の 4 つの決まりで十分です。

1. **コードにも Git にも書かない。**`.env` は `.gitignore` に入れます。リポジトリには、値を空にした `.env.example` だけを置きます。
2. **コマンドの引数に書かない。**`ps` で他のユーザーにも見えます。環境変数かファイルで渡します。
3. **ログに出さない。**デバッグで `print(os.environ)` を書くと、鍵が全部ログに載ります。出すなら先頭の数文字だけ、という上の例のような出し方にします。
4. **漏れたら失効させる。**後述の Git の節のとおり、消しても履歴は残るので、鍵そのものを無効にして作り直すのが唯一確実な対処です。

設定を環境変数で渡す考え方は、「The Twelve-Factor App」の設定の項に由来します。コードと設定を分け、同じコードを開発・本番で動かします。4 章でも、この方針で Python の設定を作ります。

## cron とタイムゾーン

cron は、時刻の書かれた表（crontab）を 1 分ごとに見て、合うコマンドを動かします。時刻は 5 つの欄、分・時・日・月・曜日で書きます。

```ini
# 分 時 日 月 曜日 コマンド
SHELL=/bin/bash
MAILTO=""
15 3 * * * /opt/neboske/bin/daily_report.sh /var/log/neboske/access.log /srv/reports >> /var/log/neboske/cron.log 2>&1
```

`15 3 * * *` は「毎日 3 時 15 分」です。`*` は「すべて」を意味します。コマンドの末尾の `>> cron.log 2>&1` で、標準出力と標準エラー出力を、ログファイルの末尾に足しています。これを書かないと、出力は捨てられるか、メールとして送られます（`MAILTO`）。失敗に気づけない cron は、動いていないのと同じです。

cron には、はまりどころがいくつかあります（Debian の `crontab(5)` と `cron(8)` による）。

- cron が用意する環境は小さく、`SHELL`・`LOGNAME`・`HOME` くらいです。自分のシェルの設定（`.bashrc`）は読まれません。`PATH` の通っていないコマンドが「見つからない」（127）になるのは、このためです。スクリプトは絶対パスで書きます。
- コマンドの中の `%` は、改行として扱われます。`date +%F` を crontab に直接書くと壊れます。`\%` と書くか、処理をスクリプトに入れます。
- コメントは、コマンドと同じ行に書けません。
- cron が扱えるタイムゾーンは 1 つだけで、その機械の設定（Debian では `/etc/timezone`）に従います。

最後の点が、データ基盤で大きな問題になります。次の例を見てください。

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

日本時間の 3 時 15 分は、UTC では前の日の 18 時 15 分です。サーバが UTC で動いていると、「日本の 1 日分」を取り込むつもりのバッチが、日付の境目で 1 日ずれます。ログの時刻が `+09:00` 付きのとき、同じ瞬間が UTC では前日の日付になるのも、この例のとおりです。

対策は次のとおりです。

- 保存する時刻は、タイムゾーン付きで UTC にそろえる。表示のときだけ日本時間にする。Airflow（12 章）も、内部では UTC で時刻を持つのが既定です。
- 「何日分を処理するか」は、実行した時刻から計算するのでなく、引数や変数で明示する。再実行しても同じ結果になります（冪等）。
- サーバのタイムゾーンを、README に書く。

## ssh

ssh は、別の機械に暗号化された通信でつなぎます。パスワードの代わりに、**鍵のペア**を使う方法が一般的です。ペアのうち、秘密鍵は手元に置き、公開鍵だけをつなぎ先に登録します。つなぐと、秘密鍵を持っている人だけが入れます。秘密鍵は誰にも渡さず、Git にも入れません。

```bash
ssh-keygen -t ed25519 -C "neboske-batch" -f ~/.ssh/id_ed25519_neboske
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519_neboske
ssh neboske-batch 'df -h /data'
scp neboske-batch:/srv/reports/errors.csv .
ssh -L 15432:localhost:5432 neboske-batch
```

`ed25519` は現在よく使われる鍵の種類です。`ssh neboske-batch '...'` のように末尾にコマンドを付けると、つないだ先でそのコマンドだけを動かします。`scp` はファイルのコピーです。`-L` は**ポートフォワード**で、手元の 15432 番を、つなぎ先から見た `localhost:5432` につなぎます。外から直接つなげない PostgreSQL に、手元の道具で入るときに使います。

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

コミットは、**1 つの目的**に対して 1 つ作ります。「注文の検証を足した」と「ログの文言を直した」は、別のコミットです。粒度が細かいと、次のことができるようになります。

- 問題が起きたとき、そのコミットだけを `git revert` で取り消せる。
- レビューする人が、変更の意図を 1 つずつ追える。
- `git log` が、そのまま変更の説明書になる。

コミットメッセージは、何を変えたかが 1 行で分かるようにします。この本のリポジトリでは `feat:`（機能）、`fix:`（修正）、`docs:`（文書）のように種類を頭に付けています。これは慣習で、Git の機能ではありません。チームのルールに合わせます。1 回のコミットに複数の目的が混ざったときは、`git add -p` で変更を部分ごとに選べます。

### ブランチとマージ

ブランチは、コミットに付ける動かせる名前です。`main` から作業用のブランチを切って変更し、できたら `main` に取り込みます。`main` は常に動く状態に保ち、作業の途中を持ち込まないための約束です。

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

ブランチの名前は、`feat/validate-orders` のように「種類/内容」にそろえると、一覧が読みやすくなります。同じ行を 2 人が別々に変えると、マージで**コンフリクト**（衝突）が起きます。ファイルに `<<<<<<<` などの印が入るので、どちらを残すか決めて印を消し、`git add` してコミットします。長く生きるブランチほど衝突が増えるので、小さく作って早く取り込みます。

### PR とレビュー

チームでは、ブランチを直接 `main` に取り込まず、**プルリクエスト（PR）**を出します。PR は、GitHub などの上で「このブランチを `main` に取り込んでよいか」を相談する場です。

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

`git push -u` は、ブランチをリモートに送り、以後の `push` の送り先を覚えさせます。`gh pr create` は GitHub の公式 CLI で PR を作ります。`git rebase origin/main` は、自分のブランチの土台を最新の `main` に付け替えます。履歴が書き換わるため、その後の `push` は `--force-with-lease` を使います。これは、自分が最後に見た状態から他の人が変えていないときだけ、上書きを許す安全版です。`main` への強制 push は、チームの決まりとして禁止します。

レビューは、バグを探す場であると同時に、知識を共有する場です。データの仕事では、次の点を見てもらいます。

- 同じ処理を 2 回動かしても、結果が変わらないか（冪等）。
- 元データの欠損、重複、遅れを考えているか。
- 秘密や個人情報が、コードやログに入っていないか。
- テストが付いているか。

レビューをお願いする側は、PR を小さくします。数百行を超えると、読む人は注意深く見られません。何のための変更かを、PR の説明に書きます。

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

`.env` が `git status` に出てきません。`data/` や `__pycache__/` のように、再生成できるものも書いておきます。注意点があります。`.gitignore` は、**まだ Git が追跡していないファイル**にしか効きません。すでにコミットしたファイルは、`.gitignore` に書いても追跡が続きます。

```bash
# 差分を見て、変更を取り消す
printf 'print("debug")\n' >> etl.py
git diff --stat
git restore etl.py
git status --short | wc -l
```

`git diff` で作業ツリーの変更を確かめ、`git restore` で最後のコミットの状態に戻しています。`restore` は未コミットの変更を捨てるので、戻す前に `diff` で中身を見ます。

```text
 etl.py | 1 +
 1 file changed, 1 insertion(+)
0
```

### 秘密をコミットしてしまったとき

誰でも一度は、`.env` や鍵を `git add` してしまいます。起きたときの手順を決めておきます。上の説明のとおり、後から消しても、履歴には残ります。

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

`.env` を追跡から外した後でも、1 つ前のコミットを指定すれば鍵がそのまま読めます。`-S` は、その文字列が増減したコミットを探すオプションで、鍵が入ったコミットを見つけられます。

手順は、順番が大事です。

1. **鍵を失効させる。**これが最優先です。公開リポジトリなら、push した時点で第三者に読まれたものとして扱います。非公開でも、クローンを持つ全員に渡ったとみなします。クラウドや API の管理画面で無効にし、新しい鍵を発行します。
2. 新しい鍵は、コードの外（環境変数や、秘密を扱う専用の仕組み）で渡す。
3. 履歴から消したいときは、`git filter-repo` などの専用のツールを使う。Git 本体の `git filter-branch` のドキュメントは、危険な点を挙げて `git filter-repo` を勧めています。履歴を書き換えると、チーム全員のクローンに影響するので、事前に相談します。
4. GitHub の場合、サポートの手順（公式ドキュメント「Removing sensitive data from a repository」）を確認する。

事前の予防もできます。GitHub には、秘密に似た文字列を含む push を受け付けない**プッシュ保護**（secret scanning の機能）があります。使える範囲はリポジトリの種類やプランで違うので、公式ドキュメントで確かめてください。

## よくある失敗

- **`uniq` の前に `sort` し忘れる。**数えた結果が静かにずれます。`sort | uniq -c` をひとまとまりで覚えます。
- **変数を引用符で囲まない。**空白を含む名前で、意図しない複数の引数に割れます。常に `"$var"` と書きます。
- **`set -e` だけで安心する。**`pipefail` と `-u` も付けます。さらに、`if` や `||` の中では効かないことを覚えておきます。
- **`rm -rf "$dir/"` で `$dir` が空。**`set -u` と `${dir:?}` で防ぎます。
- **cron で動かすと「コマンドが無い」。**自分のシェルと環境が違います。絶対パスで書き、ログに出力を残します。
- **日付がずれる。**サーバが UTC で動いていることに気づかない。時刻は UTC で保存し、処理する日付は明示します。
- **`.gitignore` に書いたのに追跡される。**追跡中のファイルは `git rm --cached` で外します。
- **秘密を消して終わりにする。**履歴に残ります。まず失効させます。
- **巨大なコミット。**1 つの PR に複数の目的を入れると、レビューも取り消しもできません。

## まとめ

- コマンドは標準入力・標準出力・標準エラー出力を持つ。パイプとリダイレクトで、小さな部品をつなげる。
- `sort | uniq -c | sort -rn` は出現回数の定型。`awk` は列の取り出しと集計、`jq` は JSON に使う。
- スクリプトの先頭には `set -euo pipefail`。結果は一時ファイルに書いて最後に `mv`、後片付けは `trap`。
- 秘密はコードの外（環境変数・ファイル）に置き、権限は最小に。引数にもログにも出さない。
- cron は、環境が小さく、タイムゾーンが 1 つしかない。時刻は UTC で持ち、処理する日付は明示する。
- Git は目的ごとに小さくコミットし、ブランチと PR で共有する。秘密を入れたら、先に失効させる。

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
    `~` は正規表現に一致するかの判定です。`grep ' /products/' access.log | awk '{print $3}' | ...` のように `grep` で先に絞っても構いません。結果が空になる場合は、パスの書き方（`/` の位置）を `head` で確かめます。

問2. 次のスクリプトは、`sort` が失敗しても「完了」と表示し、終了コード 0 で終わります。先頭に何を足せば、失敗で止まるようになりますか。また、その理由を説明してください。

```text
cat input.csv | sort | uniq > result.csv
echo "完了"
```

??? note "解答例"
    `set -euo pipefail` を先頭に足します。パイプの終了コードは、既定では最後のコマンド（`uniq`）のものだけで、`sort` が失敗しても 0 になります。`pipefail` を付けると、途中の失敗が全体の失敗になり、`set -e` がそこでスクリプトを止めます。さらに、`result.csv` は書きかけのまま残るので、本章の `daily_report.sh` のように、一時ファイルに書いて最後に `mv` する形にするとよいです。

問3. 毎日 2 時に動くバッチがあります。サーバのタイムゾーンは UTC です。日本時間の「前日 1 日分」のログを処理したいとき、何に気をつけて設計しますか。3 点挙げてください。

??? note "解答例"
    (1) サーバの 2 時は日本時間の 11 時なので、「日本の 0 時〜24 時」を対象にするなら、UTC に直すと前日の 15:00 から当日の 15:00 までになります。境目は、実行時の「今日」ではなく、引数や変数で渡した日付から計算します。(2) ログの時刻は、`+09:00` のようにタイムゾーン付きで読み、UTC か日本時間のどちらかにそろえてから日付で分けます。(3) 再実行しても同じ結果になるよう、出力は日付ごとのファイルに上書きし、追記にしません。サーバのタイムゾーンは README に書きます。

問4. 同僚が誤って `.env`（API キー入り）を含むコミットを、非公開リポジトリのブランチに push しました。まだマージされていません。取るべき手順を順番に書いてください。

??? note "解答例"
    (1) API キーを失効させ、新しいキーを発行する。ブランチを消しても、クローンや PR の履歴に残るためです。(2) `.env` を `.gitignore` に追加し、追跡から外す（`git rm --cached .env`）。(3) 新しいキーは、環境変数など、コードの外で渡す。(4) 履歴からも消したい場合は `git filter-repo` などで書き換えるが、全員のクローンに影響するのでチームに知らせてから行う。(5) 再発防止として、プッシュ保護の有効化や、`.env.example` を置く運用を検討する。

## 参考文献

- GNU Coreutils Manual: <https://www.gnu.org/software/coreutils/manual/coreutils.html>（`sort`・`uniq`・`wc`・`head`・`tail`・`date`・`mktemp`・`chmod`・`stat`）
- Bash Reference Manual: <https://www.gnu.org/software/bash/manual/bash.html>（リダイレクト、`set` の組み込みコマンド、終了ステータス、パラメータ展開）
- The GNU Awk User's Guide: <https://www.gnu.org/software/gawk/manual/gawk.html>
- jq Manual: <https://jqlang.github.io/jq/manual/>
- Debian `crontab(5)`: <https://manpages.debian.org/bookworm/cron/crontab.5.en.html> ／ `cron(8)`: <https://manpages.debian.org/bookworm/cron/cron.8.en.html>
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
