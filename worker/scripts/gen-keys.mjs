// ライセンス署名用の鍵ペア (ECDSA P-256) を作ります。
// 実行: node worker/scripts/gen-keys.mjs  (出力をファイルに保存しないでください)
//
// - 秘密鍵 (private) … `npx wrangler secret put LICENSE_PRIVATE_JWK` に貼り付けます。
//                      ファイルに保存したり、リポジトリに入れたりしないでください。
// - 公開鍵 (public)  … wrangler.toml の LICENSE_PUBLIC_JWK に貼り付けます (公開して問題ありません)。
const pair = await crypto.subtle.generateKey(
  { name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const priv = await crypto.subtle.exportKey("jwk", pair.privateKey);
const pub = await crypto.subtle.exportKey("jwk", pair.publicKey);
delete pub.key_ops;
delete pub.ext;

console.log("=== 秘密鍵 (LICENSE_PRIVATE_JWK に登録。他には保存しない) ===");
console.log(JSON.stringify(priv));
console.log("");
console.log("=== 公開鍵 (wrangler.toml の LICENSE_PUBLIC_JWK に貼る) ===");
console.log(JSON.stringify(pub));
