// 購入ボタンと Worker の接続先です。空のあいだは「準備中」と表示します。
// 2026-11-12 現在は Stripe のサンドボックス (テスト) の Payment Link です。本番に切り替えるときは docs/DEPLOY.md の手順で差し替えます。
window.DE_BOOK_CONFIG = {
  paymentLinkUrl: "https://buy.stripe.com/test_28E14g0nie2Tff19FF6g801",
  licenseApiBase: "https://de-book-license.nebourocket.workers.dev"
};
