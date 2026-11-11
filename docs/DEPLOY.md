# 公開・運用の手順

データエンジニアの本を、サーバー代ゼロで公開し、有料の応用編を配信するための手順です。
決済を有効にするまでの作業は、上から順に一度だけやれば終わります。

## 費用の考え方

- **GitHub Pages**（本の公開部分）— 公開リポジトリなら無料。
- **Cloudflare Workers + KV**（ライセンス発行と応用編の配信）— 無料プランで足ります。
- **Stripe**（決済）— 月額・初期費用はなく、売れたときに決済手数料が引かれるだけ。手数料率は Stripe の料金ページで最新の値を確認してください。

応用編の本文は非公開リポジトリ（`data-engineering-book-pro`）で管理し、KV にだけ置きます。公開リポジトリには入れません。

## 1. Stripe の準備

1. [Stripe](https://dashboard.stripe.com/register) でアカウントを作り、本人確認と入金口座の登録をすませる。
2. 「設定 → ビジネス → 公開情報」で、表示名を「寝坊ロケット」などにする。特定商取引法に基づく表記の URL も登録する。
3. **商品を作る**：「商品カタログ → 商品を追加」で、応用編の名前と価格（500円）、**1回限り**（継続ではない）。
4. **Payment Link を作る**：その商品から「支払いリンクを作成」。
   - 支払い方法：**カードのみ**（後払いの方法は、戻ってきた時点で未払いのため外す）
   - 数量の変更：**許可しない**
   - プロモーションコード：**許可しない**（金額が合わないとキーは発行されません）
   - 自動税計算（Stripe Tax）や、その他の追加手数料：**オフ**（Worker は `amount_total` がちょうど 500 のときだけキーを発行します。税や手数料が足されると 500 を超え、払ってもキーが出ません）
   - 支払い後の動作：「確認ページを表示しない → 顧客をウェブサイトにリダイレクト」にして、次の URL を入れる
     `https://nebourocket.github.io/data-engineering-book/advanced/?session_id={CHECKOUT_SESSION_ID}`
     （`{CHECKOUT_SESSION_ID}` はこのまま書きます。Stripe が本物の番号に置き換えます）
5. できた Payment Link の URL（`https://buy.stripe.com/...`）と ID（`plink_...`）を控える。
6. **制限付きキーを作る**：「開発者 → API キー → 制限付きのキーを作成」。権限は **Checkout Sessions を「読み取り」だけ**、ほかはすべて「なし」。できたキー（`rk_live_...`）は、この後すぐ Cloudflare に登録し、ほかの場所には保存しない。

最初は「テストモード」で同じ手順を踏み、テスト用カード（`4242 4242 4242 4242`）で一通り動くか確かめてから、本番モードで作り直すのがおすすめです。テストと本番では、キー・Payment Link の URL と ID がすべて別物になります。切り替えるときは、下の「テストから本番への切り替え」を必ず全部やってください。

## 2. ライセンス署名の鍵を作る

```bash
cd ~/data-engineering-book
node worker/scripts/gen-keys.mjs
```

- 「秘密鍵」の1行 → 次の手順で Cloudflare に登録する。**ファイルにもチャットにも残さない。**
- 「公開鍵」の1行 → `worker/wrangler.toml` の `LICENSE_PUBLIC_JWK` のシングルクォート ' の中に貼る（公開して問題ありません）。

## 3. Cloudflare Workers と KV を用意する

1. [Cloudflare](https://dash.cloudflare.com/sign-up) で無料アカウントを作る。
2. 応用編の本文を入れる KV を作る。表示された `id` を `worker/wrangler.toml` の `[[kv_namespaces]]`（binding は `CONTENT`）に貼る。

```bash
cd ~/data-engineering-book/worker
npx wrangler@3 login
npx wrangler@3 kv namespace create CONTENT
```

3. シークレットを登録してから公開する（Worker 名は `de-book-license`）。

```bash
cd ~/data-engineering-book/worker
npx wrangler@3 secret put STRIPE_SECRET_KEY     # rk_live_... （制限付き・Checkout Sessions 読み取りのみ）を貼る
npx wrangler@3 secret put LICENSE_PRIVATE_JWK   # 手順2の秘密鍵を貼る
npx wrangler@3 deploy
```

4. `wrangler.toml` の `[vars]` に `LICENSE_PUBLIC_JWK`（手順2の公開鍵。シングルクォート ' の中に貼る）と `PAYMENT_LINK_ID`（`plink_...`）を入れて、もう一度 `~/data-engineering-book/worker` で `npx wrangler@3 deploy`。どちらかが空のあいだは、安全のためキーも章も出しません。
5. 表示された URL（`https://de-book-license.<サブドメイン>.workers.dev`）を控える。

## 4. 本の設定を入れて公開する

`book/assets/config.js` の2つを埋めます。

```js
window.DE_BOOK_CONFIG = {
  paymentLinkUrl: "https://buy.stripe.com/...",
  licenseApiBase: "https://de-book-license.<サブドメイン>.workers.dev"
};
```

初回だけ、GitHub Pages の公開元を「GitHub Actions」にします。これをしないと、最初のデプロイが失敗します。

- 画面から：リポジトリの Settings → Pages → Source を **GitHub Actions** にする。
- コマンドから：

```bash
gh api -X POST repos/nebourocket/data-engineering-book/pages -f build_type=workflow
```

main に入ると、CI（`.github/workflows/pages.yml`）がテストとビルドを通したうえで GitHub Pages に反映します。

## 5. 応用編の更新手順

応用編の本文は非公開リポジトリで書き、KV に入れます。公開側の CI は非公開リポジトリを読めないので、**混入チェックは手元で回します**（公開前と応用編を更新したとき）。KV に入れる前にチェックします。

公開リポジトリの直下で、まずチェックします（Docker の場合）。

```bash
cd ~/data-engineering-book
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev mkdocs build --strict
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -v ~/data-engineering-book-pro:/pro:ro -w /w de-book-dev \
  python tests/check_no_paid_text.py --pro /pro/chapters --public . --site site
```

`漏れはありません` と出て終了コード 0 なら問題ありません。漏れがあると、該当の文とファイルを出して終了コード 1 になります。その場合は公開を止めて、公開側から取り除いてください。

問題なければ、KV 用の JSON を作って流し込みます。

```bash
# 非公開リポジトリの dist/kv.json を作る（Python は Docker で動かす）
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v ~/data-engineering-book-pro:/w -v ~/data-engineering-book:/public:ro -w /w -e DE_BOOK_PUBLIC=/public de-book-dev python scripts/build_kv.py --out dist/kv.json

# 公開リポジトリの worker/ で KV に流し込む
cd ~/data-engineering-book/worker
npx wrangler@3 kv bulk put ../../data-engineering-book-pro/dist/kv.json --binding CONTENT
```

## 6. 動作確認

1. 本を開き、購入ボタンが Stripe の画面に飛ぶこと。
2. テストモードなら `4242 4242 4242 4242` で支払い、応用編に戻って章が読めること。
3. 別のブラウザ（シークレットウィンドウなど）で、購入していない状態では章が出ないこと。
4. アドレスバーに `session_id` が残っていないこと。

## 払ったのにキーが出なかった人への対応

設定の誤り（金額が 500 にならない、`PAYMENT_LINK_ID` の違いなど）で、払ったのにキーが出ないことがあります。設定を直したあと、次の手順で手動発行します。

1. Stripe の「支払い」から該当の支払いを開き、Checkout Session の ID（`cs_live_...`）を控える。
2. ブラウザで `https://de-book-license.<subdomain>.workers.dev/license?session_id=<cs_live_…>` を開く（`<subdomain>` は自分の Workers のもの）。
3. 返ってきたキー（`DEB1.…`）を購入者にメールなどで送る。

## 漏えいチェックの注意

`tests/check_no_paid_text.py` は、チェックした文が 0 件だったとき（`--pro` のパスが違うときなど）に終了コード 2 で止まります。「通った」ではなく設定ミスのサインなので、パスを確かめてください。

## 失効の手順

返金や不正利用があったとき、特定の購入分だけ止められます。キーの中の `sid` は「Checkout Session ID（`cs_live_...`）の SHA-256 の先頭32桁（16進）」です。

```bash
# sid を求める（cs_live_xxx は Stripe の「支払い」で確かめた ID）
printf '%s' 'cs_live_xxx' | sha256sum | cut -c1-32

# 失効させる（公開リポジトリの worker/ で）
cd ~/data-engineering-book/worker
npx wrangler@3 kv key put --binding CONTENT "revoked:<sid>" 1
```

`revoked:<sid>` に何か値が入っていれば、そのキーでは章が配信されなくなります。元に戻すときは `npx wrangler@3 kv key delete --binding CONTENT "revoked:<sid>"`。

## テストから本番への切り替え

1. Stripe を本番モードにして、手順1の 3〜6（商品・Payment Link・制限付きキー）を作り直す。
2. **署名用の鍵も作り直す**（手順2）。`npx wrangler@3 secret put LICENSE_PRIVATE_JWK` で新しい秘密鍵に入れ替え、`wrangler.toml` の `LICENSE_PUBLIC_JWK` を新しい公開鍵にする。テスト中はテスト用カードで誰でもキーを作れたので、鍵を替えてそれらを使えなくするためです。
3. `npx wrangler@3 secret put STRIPE_SECRET_KEY` で本番のキー（`rk_live_...`）に入れ替える。
4. `wrangler.toml` の `PAYMENT_LINK_ID` を本番の `plink_...` にして、`~/data-engineering-book/worker` で `npx wrangler@3 deploy`。
5. `book/assets/config.js` の `paymentLinkUrl` を本番の URL にして main に入れる。
6. 自分で一度だけ本番で購入して、章が読めることを確かめる（その後 Stripe から自分に返金できます）。
