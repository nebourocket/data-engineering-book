# 骨組みと決済 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基礎編の章を足すだけで公開でき、応用編は Stripe で 500 円払った人だけが Worker から本文を受け取って読めるサイトの骨組みを作り、テスト環境で通しの動作まで確かめる。

**Architecture:** 公開リポジトリ `data-engineering-book` の MkDocs Material を GitHub Actions で Pages に出す。応用編は非公開リポジトリ `data-engineering-book-pro` で HTML 断片にして Workers KV に入れ、Worker `de-book-license` が署名付きキー (`DEB1.…`) を確かめてから返す。キーの発行は PFC の Worker (`~/pfc-calculator/worker/src/index.js`) と同じ方式。

**Tech Stack:** Python 3.12 (Docker イメージ `de-book-dev`)・mkdocs-material・pymdown-extensions・markdown・pytest / Cloudflare Workers・Workers KV・wrangler@3・Node 22 (依存なしのテスト) / Stripe Payment Link / Mermaid 11 (CDN)

**Spec:** `docs/superpowers/specs/2026-11-11-book-design.md`

## Global Constraints

- 名義は「寝坊ロケット」。本名・メールアドレスをコード・本文・コミットに入れない (特商法ページの問い合わせ先だけは PFC の `legal.html` と同じ表記)。
- 秘密 (`STRIPE_SECRET_KEY`・`LICENSE_PRIVATE_JWK`) は `wrangler secret` にだけ置く。ファイル・チャット・ログに出さない。
- 価格は `PRICE_JPY = "500"`、通貨 `jpy`、キーの接頭辞は `DEB1`、ECDSA P-256 / SHA-256。
- `ALLOWED_ORIGIN = "https://nebourocket.github.io"`、サイトの URL は `https://nebourocket.github.io/data-engineering-book/`。
- 章の ID は `"01"`〜`"12"` (2桁)。KV のキーは `chapter:<ID>` と `revoked:<sid>`。
- 応用編の本文は公開リポジトリに入れない。公開側の章ページの紹介文は、非公開側の本文とは別に書く (重複させない)。
- 本文の表は手で打たない (`data/tables/*.csv` から hook で作る)。
- コミットに AI の帰属表示を入れない。コメントは丁寧な日本語、画面に出る文字は日本語の本文に合わせて日本語。
- Python は Docker 内で動かす: `docker run --rm -v "$PWD":/w -w /w de-book-dev <コマンド>` (以下 `DEV` と書く)。

## Review Focus

1. キーを貼るときに前後の空白や改行が付く → 取り除いて受け付ける (Task 4 `normalizeLicense` のテスト)。
2. localStorage が使えない (プライベートモード等) → 落ちずに、その場で貼ったキーで今のページは読める (Task 4 `makeStore` のテスト)。
3. Stripe から戻ったが未払い・別商品の `session_id` → 「支払いを確認できませんでした」と出し、URL から `session_id` を消す (Task 3 の 402 テスト + Task 4 `stripSessionId` のテスト)。
4. まだ KV に入れていない章を開く → 404 を受けて「この章は準備中です」と出す (Task 3 の 404 テスト + Task 4 の応答の振り分けテスト)。
5. 失効したキーが localStorage に残っている → 401 を受けて保存キーを消し、購入ボタンとキー入力欄に戻す (Task 3 の失効テスト + Task 4 の応答の振り分けテスト)。

---

### Task 1: リポジトリの骨組みと開発用イメージ

**Files:**
- Create: `Dockerfile`, `requirements.txt`, `mkdocs.yml`, `book/index.md`, `book/basics/index.md`, `book/advanced/index.md`, `README.md`, `.gitignore`
- Modify: `docs/superpowers/specs/2026-11-11-book-design.md` (Worker のテストを「Node のみ」に、応用編の Mermaid を「差し込み後に pro.js が描く」に直す)

**Interfaces:**
- Produces: イメージ `de-book-dev` (`docker build -t de-book-dev .`)。`mkdocs.yml` の `docs_dir: book`、`hooks: [hooks/tables.py]` (Task 2 で作る。Task 1 の時点では書かない)、`extra_javascript: [assets/config.js, assets/pro.js]` (Task 4 で足す)。

- [ ] **Step 1:** `requirements.txt` にバージョンを固定して書く: `mkdocs-material==9.5.49`, `pymdown-extensions==10.12`, `markdown==3.7`, `pytest==8.3.4`。`Dockerfile` は `python:3.12-slim` から `pip install -r requirements.txt` するだけ。
- [ ] **Step 2:** `mkdocs.yml`: `site_name: データエンジニアの本`, `site_url: https://nebourocket.github.io/data-engineering-book/`, `site_author: 寝坊ロケット`, `docs_dir: book`, `theme: material` (`language: ja`、Nord の色 `#88C0D0` / `#5E81AC` を `extra_css` で上書き、ライト/ダーク切り替え、`navigation.tabs` `navigation.sections` `navigation.footer` `search.suggest` `content.code.copy`)、`markdown_extensions`: `tables`, `admonition`, `pymdownx.details`, `pymdownx.highlight`, `pymdownx.superfences` (mermaid の custom_fence), `pymdownx.tabbed`, `footnotes`, `md_in_html`, `toc` (`permalink: true`)。`nav` は「はじめに / 基礎編 / 応用編 / 特定商取引法に基づく表記」の4つ。
- [ ] **Step 3:** `book/index.md` に本の目的・読み方・前提知識・環境 (Docker) を短く書く。`basics/index.md` と `advanced/index.md` に仕様書 4 章の章立て表の代わりに章の一覧 (リスト) を置く (表は CSV にするため、ここではリスト)。
- [ ] **Step 4:** `README.md` に目的・使い方 (`docker build`・`DEV mkdocs serve -a 0.0.0.0:8000`・テスト) と「🤖 AI への注意」(応用編の本文はこのリポジトリに入れない・表は CSV・秘密は wrangler secret) を書く。
- [ ] **Step 5:** 検証。Run: `docker build -t de-book-dev . && DEV mkdocs build --strict` → Expected: `Documentation built` が出て、終了コード 0。
- [ ] **Step 6:** Commit: `git add Dockerfile requirements.txt mkdocs.yml book README.md .gitignore docs/superpowers/specs/2026-11-11-book-design.md && git commit -m "feat: MkDocs の骨組みと開発用イメージ"`

### Task 2: CSV から表を作る hook

**Files:**
- Create: `hooks/tables.py`, `tests/test_tables.py`, `data/tables/basics-sample.csv` (テスト用ではなく、`book/index.md` で使う「基礎編と応用編のちがい」の表)
- Modify: `mkdocs.yml` (`hooks: [hooks/tables.py]`), `book/index.md` (`{{ table("basics-sample") }}` を1つ使う)

**Interfaces:**
- Produces (Task 5 も import する):
  - `TABLE_RE`: `\{\{\s*table\("([a-z0-9-]+)"\)\s*\}\}`
  - `render_table(name: str, tables_dir: Path) -> str` — CSV (UTF-8、1行目が見出し) を Markdown の表にして返す。`|` はエスケープ。ファイルが無ければ `FileNotFoundError`。
  - `expand_tables(markdown: str, tables_dir: Path) -> str` — 本文中の `{{ table("…") }}` をすべて置き換える。
  - `on_page_markdown(markdown, page, config, files)` — `tables_dir = Path(config["config_file_path"]).parent / "data" / "tables"` で `expand_tables` を呼ぶ。

- [ ] **Step 1: 失敗するテストを書く** (`tests/test_tables.py`)
  - `test_render_basic`: `a,b\n1,2\n` → `"| a | b |\n| --- | --- |\n| 1 | 2 |\n"`
  - `test_render_escapes_pipe`: セル `x|y` → 出力に `x\|y`
  - `test_missing_raises`: 無い名前で `pytest.raises(FileNotFoundError)`
  - `test_expand_replaces_all_and_keeps_text`: `前\n{{ table("t") }}\n後` → 前と後が残り、表が入る
  - `test_expand_ignores_other_braces`: `{{ other }}` はそのまま
- [ ] **Step 2:** Run: `DEV pytest tests/test_tables.py -v` → Expected: FAIL (`ModuleNotFoundError: hooks`)
- [ ] **Step 3:** `hooks/tables.py` を実装する (標準ライブラリの `csv` だけ使う)。`tests/conftest.py` でリポジトリ直下を `sys.path` に足す。
- [ ] **Step 4:** Run: `DEV pytest tests/test_tables.py -v` → Expected: 5 passed。続けて `DEV mkdocs build --strict` → 終了コード 0 で、`grep -c "<table" site/index.html` が 1 以上。
- [ ] **Step 5:** Commit: `git add hooks tests data mkdocs.yml book/index.md && git commit -m "feat: CSV から表を作る hook"`

### Task 3: Worker `de-book-license`

**Files:**
- Create: `worker/src/index.js`, `worker/test/worker.test.mjs`, `worker/scripts/gen-keys.mjs` (PFC のものをコピーして、出力に公開鍵 JWK も出す), `worker/wrangler.toml`, `worker/package.json`

**Interfaces:**
- Consumes: PFC の `issueLicense` / `isPaidSession` / `corsHeaders` の作り (コピーして直す)。
- Produces:
  - `issueLicense(sessionId: string, privateJwkText: string, now?: number) -> Promise<string>` — `DEB1.<payload>.<sig>`
  - `verifyLicense(license: string, publicJwkText: string) -> Promise<{v:1,sid:string,iat:number}|null>` — 形・署名・`v===1` のどれかが違えば `null`
  - `isPaidSession(session, env) -> boolean` — PFC と同じ7条件
  - HTTP: `GET /license?session_id=` → 200 `{license}` / 400 `bad_session_id` / 402 `not_paid` / 404 `session_not_found` / 500 `not_configured` / 502 `stripe_error`。`GET /chapter/<01-12>` (`Authorization: Bearer <key>`) → 200 `text/html` / 401 `invalid_license` (無い・壊れた・失効) / 404 `chapter_not_found` / 400 `bad_chapter`。他は 404 `not_found`、GET 以外は 405。
  - env: `STRIPE_SECRET_KEY`, `LICENSE_PRIVATE_JWK` (secret)、`LICENSE_PUBLIC_JWK`, `ALLOWED_ORIGIN`, `PRICE_JPY`, `PAYMENT_LINK_ID` (vars)、`CONTENT` (KV binding)。
  - CORS: `Access-Control-Allow-Methods: GET, OPTIONS`、`Access-Control-Allow-Headers: Authorization`。本文の応答は `Cache-Control: private, no-store`。

- [ ] **Step 1: 失敗するテストを書く** (`worker/test/worker.test.mjs`、PFC の `license.test.mjs` と同じ `check()` 形式、Stripe はフェイクの fetch、KV は `{ get: async (k) => map.get(k) ?? null }`)
  - 発行: 支払い済み → 200 で `license` が `DEB1.` で始まり、`verifyLicense` で `sid` が32桁
  - 未払い・金額 499・`usd`・別の `payment_link`・`PAYMENT_LINK_ID` 空 → それぞれ 402 (空は 500 `not_configured`)
  - `session_id` が `abc` → 400、Stripe が 404 → 404、Stripe が 500 → 502
  - 章: 正しいキー + KV に `chapter:01` → 200 で本文、`Cache-Control` に `no-store`
  - キーなし・形の違うキー・payload を1文字変えたキー・別の鍵で署名したキー → 401
  - `revoked:<sid>` が KV にある → 401
  - KV に無い `chapter:02` → 404、`/chapter/13` と `/chapter/1` → 400
  - CORS: `Origin` が `ALLOWED_ORIGIN` のときだけ `Access-Control-Allow-Origin`、`OPTIONS` は 204 で `Allow-Headers` に `Authorization`
- [ ] **Step 2:** Run: `node worker/test/worker.test.mjs` → Expected: import で失敗
- [ ] **Step 3:** `worker/src/index.js` を実装する。署名の確認は `crypto.subtle.verify({name:"ECDSA",hash:"SHA-256"}, pub, sig, "DEB1.<payload>")`。base64url の復号に失敗したら `null`。
- [ ] **Step 4:** Run: `node worker/test/worker.test.mjs` → Expected: 全項目 `ok`、`NG` 0、終了コード 0
- [ ] **Step 5:** `wrangler.toml`: `name = "de-book-license"`、vars は上のとおり (`PAYMENT_LINK_ID = ""`、`LICENSE_PUBLIC_JWK = ""` で始める)、`[[kv_namespaces]] binding = "CONTENT"` (id は Task 7 で入れる)。
- [ ] **Step 6:** Commit: `git add worker && git commit -m "feat: キー発行と応用編配信の Worker"`

### Task 4: 応用編のページと `pro.js`

**Files:**
- Create: `book/assets/pro-core.js`, `book/assets/pro.js`, `book/assets/config.js`, `book/advanced/01-distributed-processing.md` … `12-platform-and-organization.md` (紹介文だけ), `book/legal.md`, `tests/pro-core.test.mjs`
- Modify: `mkdocs.yml` (`extra_javascript` に `assets/config.js`、`assets/pro.js` を `type: module` で、nav に応用編12章と legal)

**Interfaces:**
- Consumes: Task 3 の HTTP API。
- Produces:
  - `config.js`: `window.DE_BOOK_CONFIG = { paymentLinkUrl: "", licenseApiBase: "" }` (Task 7 で埋める。空のあいだは購入ボタンを出さない)
  - `pro-core.js` (ESM、DOM を触らない):
    - `normalizeLicense(text: string) -> string|null` — 空白・改行を除き、`/^DEB1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/` なら返す
    - `sessionIdFromUrl(href: string) -> string|null` / `stripSessionId(href: string) -> string`
    - `makeStore(storage) -> {get():string|null, set(v), clear()}` — `storage` が例外を投げても、メモリに持って動く
    - `chapterState(status: number) -> "ok"|"invalid"|"missing"|"error"` — 200/401/404/その他
  - 章ページの印: `<div class="pro-chapter" data-chapter="01" markdown></div>` を紹介文の後に置く。`advanced/index.md` には `<div class="pro-buy"></div>`。
  - localStorage のキー名: `"deb-license"`。
  - `pro.js`: 起動時に `session_id` があれば `/license` を呼んでキーを保存・表示し、URL から消す。`.pro-chapter` があれば `/chapter/<id>` を取り、`ok` なら差し込み、`<pre class="mermaid">` があれば `https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs` を import して `mermaid.run({nodes})`。`invalid` ならキーを消して購入欄、`missing` なら「この章は準備中です」。
  - 画面の文言: 「500円で応用編を買う (買い切り)」「購入済みの方はキーを貼り付けてください」「この章は準備中です」「支払いを確認できませんでした。時間をおいてもう一度開くか、お問い合わせください」「あなたのキー (別の端末で使うときに貼り付けます)」

- [ ] **Step 1: 失敗するテストを書く** (`tests/pro-core.test.mjs`、Node のみ)
  - `normalizeLicense("  DEB1.ab.cd\n")` → `"DEB1.ab.cd"`、`"PFC1.ab.cd"`・`"DEB1.ab"`・`""` → `null`
  - `sessionIdFromUrl(".../advanced/?session_id=cs_test_x")` → `"cs_test_x"`、無ければ `null`。`stripSessionId` は他のクエリと `#hash` を残す
  - `makeStore` に `getItem`/`setItem` が例外を投げる storage を渡しても、`set("k")` の後 `get()` が `"k"`
  - `chapterState(200/401/404/500)` → `ok/invalid/missing/error`
- [ ] **Step 2:** Run: `node tests/pro-core.test.mjs` → Expected: import で失敗
- [ ] **Step 3:** `pro-core.js` を実装し、`pro.js` をその上に書く。`legal.md` は `~/pfc-calculator/legal.html` の項目と問い合わせ先を写し、商品名・価格・引き渡し時期 (支払い後すぐ、キーの表示による)・返品 (デジタル商品のため不可、二重購入などは問い合わせ) を本に合わせる。
- [ ] **Step 4:** 応用編12章の紹介文 (各 200〜400 字、仕様書 4 章の「できるようになること」を広げたもの) を書く。
- [ ] **Step 5:** Run: `node tests/pro-core.test.mjs && DEV mkdocs build --strict` → Expected: 全項目 ok、ビルド成功、`ls site/advanced` に 12 章のフォルダ
- [ ] **Step 6:** Commit: `git add book mkdocs.yml tests/pro-core.test.mjs && git commit -m "feat: 応用編のページと購入・キー・本文読み込み"`

### Task 5: 非公開リポジトリと KV 用のビルド

**Files (リポジトリ `~/data-engineering-book-pro`):**
- Create: `README.md` (🤖 AI への注意: 公開リポジトリに本文を写さない)、`chapters/01-distributed-processing.md` (仮の本文: 見出し・段落・表1つ・Mermaid 1つ・コード1つ。通しの確認用で、Task 7 のあと執筆計画で書き直す)、`data/tables/`、`scripts/build_kv.py`、`tests/test_build_kv.py`

**Interfaces:**
- Consumes: 公開リポジトリの `hooks/tables.py` の `expand_tables` (`--public <path>` で場所を受け取り `sys.path` に足して import する。コピーしない)。
- Produces:
  - `build_chapter_html(md_text: str, tables_dir: Path) -> str` — `expand_tables` → `markdown.markdown(..., extensions=["tables","admonition","footnotes","pymdownx.superfences","pymdownx.highlight","toc"])`。Mermaid は `<pre class="mermaid">…</pre>`。
  - `build_kv(chapters_dir: Path, tables_dir: Path) -> list[dict]` — `[{"key":"chapter:01","value":"<html>"}…]`、ファイル名の先頭2桁が ID。`01`〜`12` 以外の名前は `ValueError`。
  - CLI: `python scripts/build_kv.py --public ../data-engineering-book --out dist/kv.json` (`dist/` は `.gitignore`)

- [ ] **Step 1: 失敗するテストを書く**: 表が `<table>` になる・Mermaid が `<pre class="mermaid">`・コードが `<pre>`・`build_kv` のキーが `chapter:01`・`13-x.md` で `ValueError`
- [ ] **Step 2:** Run: `docker run --rm -v ~/data-engineering-book-pro:/w -v ~/data-engineering-book:/public -w /w de-book-dev pytest -v` → Expected: FAIL
- [ ] **Step 3:** 実装する
- [ ] **Step 4:** 同じコマンドで PASS。続けて CLI を実行し、`dist/kv.json` に `chapter:01` が1件
- [ ] **Step 5:** `git init -b main` してから Commit: `git add README.md chapters data scripts tests .gitignore && git commit -m "feat: 応用編を KV 用 HTML にするビルド"`

### Task 6: 有料本文の混入チェックと CI

**Files (公開リポジトリ):**
- Create: `tests/check_no_paid_text.py`, `tests/test_check_no_paid_text.py`, `.github/workflows/pages.yml`, `docs/DEPLOY.md`

**Interfaces:**
- Produces:
  - `extract_samples(md_text: str) -> list[str]` — 見出し・コード・表・Mermaid・リンクだけの行を除き、30字以上の段落の行を返す
  - `find_leaks(samples: list[str], roots: list[Path]) -> list[tuple[str, Path]]` — `.md` `.html` `.js` `.csv` を探す
  - CLI: `python tests/check_no_paid_text.py --pro ../data-engineering-book-pro/chapters --public . --site site` → 漏れがあれば行とファイルを出して終了コード 1
  - CI は非公開リポジトリを読めないので、このチェックは手元 (公開前と応用編の更新時) で回す。`DEPLOY.md` に書く。

- [ ] **Step 1: 失敗するテストを書く**: 見出しとコードが除かれる・30字未満が除かれる・`tmp_path` に同じ文を置くと1件見つかる・無ければ0件
- [ ] **Step 2:** `DEV pytest tests/test_check_no_paid_text.py -v` → FAIL
- [ ] **Step 3:** 実装する
- [ ] **Step 4:** PASS を確かめ、実データで Run: `docker run --rm -v ~/data-engineering-book:/w -v ~/data-engineering-book-pro:/pro -w /w de-book-dev python tests/check_no_paid_text.py --pro /pro/chapters --public . --site site` → Expected: `漏れはありません` と終了コード 0
- [ ] **Step 5:** `pages.yml`: push と PR で `pip install -r requirements.txt` → `pytest` → `node tests/pro-core.test.mjs` → `node worker/test/worker.test.mjs` → `mkdocs build --strict`。main への push のときだけ `actions/upload-pages-artifact@v3` → `actions/deploy-pages@v4`。
- [ ] **Step 6:** `DEPLOY.md` を PFC の `docs/DEPLOY.md` の形で書く (Stripe の商品・Payment Link・制限付きキー、鍵の生成、KV の作成、secret 登録、デプロイ、応用編の更新手順、失効の手順、テストから本番への切り替え)。
- [ ] **Step 7:** Commit: `git add tests .github docs/DEPLOY.md && git commit -m "feat: 有料本文の混入チェックと Pages の CI"`

### Task 7: 公開とテスト環境での通し確認 (ユーザーと一緒に)

**Files:**
- Modify: `worker/wrangler.toml` (KV の id・`PAYMENT_LINK_ID`・`LICENSE_PUBLIC_JWK`)、`book/assets/config.js`

- [ ] **Step 1:** 公開範囲の確認をユーザーに取ってから `gh repo create nebourocket/data-engineering-book --public --source . --push` と `gh repo create nebourocket/data-engineering-book-pro --private --source ~/data-engineering-book-pro --push`。Pages の公開元を GitHub Actions にする (`gh api -X POST repos/nebourocket/data-engineering-book/pages -f build_type=workflow`)。
- [ ] **Step 2:** Stripe MCP (サンドボックス) で商品「データエンジニアの本 応用編 (買い切り)」500 円・1回限り、Payment Link (カードのみ・数量変更なし・プロモコードなし・支払い後 `https://nebourocket.github.io/data-engineering-book/advanced/?session_id={CHECKOUT_SESSION_ID}`) を作る。MCP が使えなければユーザーがダッシュボードで作る。
- [ ] **Step 3:** ユーザーのターミナルで: `node worker/scripts/gen-keys.mjs` → 公開鍵を `wrangler.toml` に、秘密鍵を `npx wrangler@3 secret put LICENSE_PRIVATE_JWK` に。制限付きキー (Checkout Sessions 読み取りのみ・テスト) を `secret put STRIPE_SECRET_KEY`。`npx wrangler@3 kv namespace create CONTENT` の id を `wrangler.toml` に。
- [ ] **Step 4:** `npx wrangler@3 deploy`、非公開リポジトリで `build_kv.py` → `npx wrangler@3 kv bulk put --binding CONTENT dist/kv.json` (`worker/` から)。`config.js` を埋め、PR 経由で main に入れて Pages に反映。
- [ ] **Step 5:** 通し確認 (Playwright): 購入ボタン → Stripe テストカード `4242 4242 4242 4242` → 戻って URL に `session_id` が無い・キーが表示される → 応用編1章の本文と表と Mermaid の図が出る → 別のコンテキストでキーを貼って読める → 2章は「準備中」→ キーを1文字変えると購入欄に戻る。
- [ ] **Step 6:** Task 6 の混入チェックを公開サイトのビルドに対してもう一度回す。結果をユーザーに報告し、knowledge 側のメモリに構成を1件書く。

本番の Stripe への切り替えは、章がある程度そろってから `DEPLOY.md` の手順で行う (この計画の範囲外)。章の執筆は別の計画 (`docs/superpowers/plans/` に執筆計画として作る) で行う。
