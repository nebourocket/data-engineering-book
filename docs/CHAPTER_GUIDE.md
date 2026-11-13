# 章の書き方ガイド

基礎編の章を書く人（人も AI も）向けです。守れているかは `pytest`（`tests/test_chapters.py`）が確かめます。

## 構成（見出しは固定）

```text
---（執筆が終わるまで status: draft）
# 第N章 タイトル
## この章でできるようになること
## （本論の節 ×複数）
## よくある失敗
## まとめ
## 練習問題      ← 3 問以上。答えは ??? note "解答例" に書く
## 参考文献
```

- ファイル名は `book/basics/NN-英語のスラッグ.md`（固定。`mkdocs.yml` の nav と `basics/index.md` に登録済み）。
- 仮ページは front matter に `status: draft` を付けます。draft は構成・長さ・コードの検査を免除されますが、表（手書き表の禁止・CSV の存在）と用語表記（glossary）の検査は draft にも適用されます。書き終えたら `status: draft` を消します。
- 章末に関連する応用編があれば、最後の本文として「さらに深く: 応用編 第N章 『…』」の 1 行を置きます。

## 長さ

数えるのは、front matter とコードブロック（囲いごと）と `{{ table(...) }}` の差し込みを除いた本文の、空白・改行を除いた文字数です。見出し・箇条書き・練習問題と解答例の文章は数えます。基礎編は 7,000〜16,000 字、応用編は 10,000〜20,000 字で、範囲は `hooks/chapter_check.py` の引数で変えられます。

## 表

- 本文に Markdown の表を手で書きません（`|---` を含む行は検査で失敗します）。
- 表は `data/tables/名前.csv`（UTF-8、1 行目が見出し）に書き、本文では `{{ table("名前") }}` と書きます。参照した CSV が無いと失敗します。

## 図

- 図は手で描かず、コードから作ります。`examples/figures/*.py` を置くと、`mkdocs build` の前に全部実行されます。各スクリプトは SVG を `book/assets/figures/` に書きます（git には入れません）。
- 図のスクリプトは `from _style import use_japanese_font` で日本語フォントを設定し、ラベルは日本語で書きます（`hooks/figures.py` が `python examples/figures/名前.py` で実行するため、スクリプトのあるフォルダが import パスに入り、`_` で始まるファイルは実行されません）。
- 本文からは `![説明](../assets/figures/名前.svg)` で参照します。仕組みの流れ図は ```` ```mermaid ```` でも構いません。
- 数値を本文に手で写さないでください。揺れるためです。

## コード

- 本文のコードブロックは、`examples/bNN/`（NN は章番号）のどれか 1 つのファイルに、空白を無視してそのまま含まれていなければなりません（複数ファイルにまたがる一致は認めません）。20 文字未満の短いブロックは、前後が空白の語として一致する必要があります。先に examples に置いて動かし、そこから本文へ写します。
- 言語の指定は必須です。検査する言語は `python` `sql` `bash` `yaml` `toml` `dockerfile` `ini` `json` です。別名は次のとおり正規化されます: `py`→python、`sh` `shell` `zsh`→bash、`yml`→yaml、`docker`→dockerfile、`postgresql` `pgsql` `psql`→sql、`{.python}` の形も可。
- `console` は bash として検査しますが、`$ ` で始まる行（と行末 `\` で続く行）だけが対象で、その後の出力行は無視されます。
- 構文も確かめます（一致するだけでは、末尾が欠けたブロックも通ってしまうため）。`python` は `ast.parse`、`bash`（`console` の `$ ` 行を含む）は `bash -n`、`json` は `json.loads`、`yaml` は PyYAML があれば読み込めることが必要です（python と bash は全体が同じ幅でインデントされた断片なら、インデントを外して確かめます）。`sql` `toml` `dockerfile` `ini` は構文を確かめません。
- 途中から始まる・途中で終わる抜粋は、info 文字列に `excerpt` を付けると構文検査だけ免除されます（例: ```` ```python title="load.py" excerpt ````）。examples との一致は引き続き必要です。
- 検査の対象外は `text` `mermaid` `output` だけです。言語の指定がない、または上に無い言語（例: rust）のブロックはエラーです。コードブロックを閉じ忘れてもエラーです。
- 共通の題材は架空の「ねぼすけ商店」です（`examples/common/neboske_shop.py`）。顧客・商品・注文・明細・行動ログを作り、重複・欠損・遅延といった欠陥を意図的に含みます。`write_duckdb` と `write_parquet` で書き出せます。
- PostgreSQL・MinIO・Redpanda が要るコードは `examples/conftest.py` のフィクスチャ（`pg_dsn` `s3_client` `kafka_bootstrap`）で試します。

## 出典

- まず手元の本を探します: `/mnt/c/knowledge/books/INDEX.md`（PDF は `pages` を指定して読む）。次に公式ドキュメント、最後に Web。
- 事実や数値には、章末の「参考文献」に出典を書きます。確かめていないことは書きません。

## 文体

- です・ます調で、平易な言葉を使います。仕組みの説明が先、道具の使い方が後です。具体例を 1 つ添えます。
- 誇張（「圧倒的」「革命的」など）、AI らしい決まり文句、作り話の体験談は書きません。
- 用語は `data/glossary.csv` に従います（列 `正,誤`）。「誤」の表記が本文にあると失敗します。新しく揺れそうな用語は行を足します。

## 検査の動かし方

```bash
docker build -t de-book-dev .
alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'
DEV pytest                    # 章の検査・データセット・図の hook
DEV mkdocs build --strict     # サイトのビルド
DE_BOOK_FINAL=1 DEV pytest    # 公開前: draft が残っていれば失敗
```

サービス付きのテストは README の「サービスを使う章」を参照してください。
