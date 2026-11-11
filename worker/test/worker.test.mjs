// ライセンス発行・応用編配信 Worker のテスト (Stripe への通信と KV はフェイクに差し替えます)
// 実行: node worker/test/worker.test.mjs
import worker, { isPaidSession, issueLicense, verifyLicense } from "../src/index.js";

let passed = 0;
let failed = 0;
function check(name, cond) {
  if (cond) { passed += 1; console.log("  ok - " + name); }
  else { failed += 1; console.log("  NG - " + name); }
}

async function makePair() {
  const pair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
  return {
    priv: JSON.stringify(await crypto.subtle.exportKey("jwk", pair.privateKey)),
    pub: JSON.stringify(await crypto.subtle.exportKey("jwk", pair.publicKey)),
  };
}
const main = await makePair();
const other = await makePair();

const kv = new Map();
const CONTENT = { get: async (k) => kv.get(k) ?? null };

const ORIGIN = "https://nebourocket.github.io";
const env = {
  STRIPE_SECRET_KEY: "rk_test_dummy",
  LICENSE_PRIVATE_JWK: main.priv,
  LICENSE_PUBLIC_JWK: main.pub,
  ALLOWED_ORIGIN: ORIGIN,
  PRICE_JPY: "500",
  PAYMENT_LINK_ID: "plink_123",
  CONTENT,
};
const SID = "cs_test_a1B2c3D4e5F6g7H8i9J0";
const paid = {
  object: "checkout.session", mode: "payment", status: "complete",
  payment_status: "paid", currency: "jpy", amount_total: 500, payment_link: "plink_123",
};

let stripeCalls = [];
let stripeReply = () => new Response(JSON.stringify(paid), { status: 200 });
globalThis.fetch = async (url, init) => {
  stripeCalls.push({ url: String(url), init });
  return stripeReply();
};

function get(path, { origin, auth, e } = {}) {
  const headers = {};
  if (origin) headers.Origin = origin;
  if (auth !== undefined) headers.Authorization = auth;
  return worker.fetch(new Request("https://de-book-license.example.workers.dev" + path, { headers }), e || env);
}

console.log("[支払い済みの判定]");
check("500円・支払い済みは true", isPaidSession(paid, env));
check("金額 499 は false", !isPaidSession({ ...paid, amount_total: 499 }, env));
check("通貨 usd は false", !isPaidSession({ ...paid, currency: "usd" }, env));
check("未払いは false", !isPaidSession({ ...paid, payment_status: "unpaid" }, env));
check("未完了は false", !isPaidSession({ ...paid, status: "open" }, env));
check("サブスクは false", !isPaidSession({ ...paid, mode: "subscription" }, env));
check("別の Payment Link は false", !isPaidSession({ ...paid, payment_link: "plink_other" }, env));
check("PAYMENT_LINK_ID が空なら false",
  !isPaidSession({ ...paid, payment_link: null }, { ...env, PAYMENT_LINK_ID: "" }));
check("null は false", !isPaidSession(null, env));

console.log("[発行]");
let license;
{
  stripeCalls = [];
  const res = await get("/license?session_id=" + SID, { origin: ORIGIN });
  const body = await res.json();
  license = body.license;
  check("支払い済みなら 200", res.status === 200);
  check("ライセンスキーが DEB1. で始まる", typeof license === "string" && license.startsWith("DEB1."));
  const p = await verifyLicense(license, main.pub);
  check("verifyLicense で sid が 32 桁", !!p && p.v === 1 && /^[0-9a-f]{32}$/.test(p.sid));
  check("Stripe に 1 回だけ問い合わせる", stripeCalls.length === 1);
  check("Authorization ヘッダーで送る", stripeCalls[0].init.headers.Authorization === "Bearer rk_test_dummy");
  check("許可した Origin には CORS ヘッダーを返す", res.headers.get("Access-Control-Allow-Origin") === ORIGIN);
  check("キャッシュさせない", res.headers.get("Cache-Control") === "no-store");
  check("個人情報や Session ID が入らない", !atob(license.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")).includes(SID));
}

console.log("[発行の拒否]");
{
  stripeReply = () => new Response(JSON.stringify({ ...paid, payment_status: "unpaid" }), { status: 200 });
  check("未払いは 402", (await get("/license?session_id=" + SID)).status === 402);
  stripeReply = () => new Response(JSON.stringify({ ...paid, amount_total: 499 }), { status: 200 });
  check("金額 499 は 402", (await get("/license?session_id=" + SID)).status === 402);
  stripeReply = () => new Response(JSON.stringify({ ...paid, currency: "usd" }), { status: 200 });
  check("usd は 402", (await get("/license?session_id=" + SID)).status === 402);
  stripeReply = () => new Response(JSON.stringify({ ...paid, payment_link: "plink_other" }), { status: 200 });
  check("別の payment_link は 402", (await get("/license?session_id=" + SID)).status === 402);

  stripeReply = () => new Response(JSON.stringify(paid), { status: 200 });
  stripeCalls = [];
  const empty = await get("/license?session_id=" + SID, { e: { ...env, PAYMENT_LINK_ID: "" } });
  const emptyBody = await empty.json();
  check("PAYMENT_LINK_ID が空なら 500 not_configured", empty.status === 500 && emptyBody.error === "not_configured");
  check("PAYMENT_LINK_ID が空なら Stripe に問い合わせない", stripeCalls.length === 0);

  stripeCalls = [];
  check("session_id が abc は 400", (await get("/license?session_id=abc")).status === 400);
  check("形式が違えば Stripe に問い合わせない", stripeCalls.length === 0);

  stripeReply = () => new Response(JSON.stringify({ error: { message: "secret detail" } }), { status: 404 });
  const nf = await get("/license?session_id=" + SID);
  check("Stripe が 404 なら 404", nf.status === 404);
  check("Stripe のエラー文を返さない", !(await nf.text()).includes("secret detail"));
  stripeReply = () => new Response("oops", { status: 500 });
  check("Stripe が 500 なら 502", (await get("/license?session_id=" + SID)).status === 502);
  stripeReply = () => { throw new Error("network"); };
  check("Stripe に届かなければ 502", (await get("/license?session_id=" + SID)).status === 502);
  stripeReply = () => new Response("<html>", { status: 200 });
  check("JSON でなければ 502", (await get("/license?session_id=" + SID)).status === 502);
  stripeReply = () => new Response(JSON.stringify(paid), { status: 200 });
  const bad = await get("/license?session_id=" + SID, { e: { ...env, LICENSE_PRIVATE_JWK: "{broken" } });
  check("秘密鍵が壊れていても 500", bad.status === 500);
}

console.log("[verifyLicense]");
{
  const [pre, pl, sig] = license.split(".");
  check("正しいキーは通る", (await verifyLicense(license, main.pub)) !== null);
  check("別の鍵の公開鍵では null", (await verifyLicense(license, other.pub)) === null);
  const tampered = pre + "." + pl.slice(0, -1) + (pl.slice(-1) === "A" ? "B" : "A") + "." + sig;
  check("payload を 1 文字変えると null", (await verifyLicense(tampered, main.pub)) === null);
  check("PFC1 の接頭辞は null", (await verifyLicense("PFC1." + pl + "." + sig, main.pub)) === null);
  check("形が違えば null", (await verifyLicense("abc", main.pub)) === null);
  check("空文字は null", (await verifyLicense("", main.pub)) === null);
  check("base64url でない署名でも例外にならず null", (await verifyLicense(pre + "." + pl + ".%%%", main.pub)) === null);
  check("公開鍵が壊れていても null", (await verifyLicense(license, "{broken")) === null);
  check("公開鍵が空でも null", (await verifyLicense(license, "")) === null);
  // 署名は正しいが v が 2 の payload は拒否されること
  const b64u = (buf) => Buffer.from(buf).toString("base64url");
  const v2Body = b64u(new TextEncoder().encode(JSON.stringify({ v: 2, sid: "a".repeat(32), iat: 1 })));
  const signKey = await crypto.subtle.importKey("jwk", JSON.parse(main.priv),
    { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const v2Sig = b64u(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, signKey,
    new TextEncoder().encode(pre + "." + v2Body)));
  check("v:2 の payload は署名が正しくても null", (await verifyLicense(pre + "." + v2Body + "." + v2Sig, main.pub)) === null);
  check("ドット区切りが 4 つ以上なら null", (await verifyLicense(license + ".x", main.pub)) === null);
  check("署名が空なら null", (await verifyLicense(pre + "." + pl + ".", main.pub)) === null);
  const v2 = await issueLicense("cs_test_x", main.priv, 1000);
  check("issueLicense は DEB1 を返す", v2.startsWith("DEB1."));
}

console.log("[章の配信]");
{
  kv.set("chapter:01", "<h1>第1章</h1>");
  const ok = await get("/chapter/01", { origin: ORIGIN, auth: "Bearer " + license });
  check("正しいキーで 200", ok.status === 200);
  check("本文が返る", (await ok.text()) === "<h1>第1章</h1>");
  check("Content-Type は text/html", ok.headers.get("Content-Type") === "text/html; charset=utf-8");
  check("Cache-Control は private, no-store", ok.headers.get("Cache-Control") === "private, no-store");
  check("nosniff が付く", ok.headers.get("X-Content-Type-Options") === "nosniff");
  check("CORS が付く", ok.headers.get("Access-Control-Allow-Origin") === ORIGIN);

  const ws = await get("/chapter/01", { auth: "Bearer   " + license + "  " });
  check("前後の空白は許容", ws.status === 200);

  const none = await get("/chapter/01");
  const noneBody = await none.json();
  check("キーなしは 401", none.status === 401 && noneBody.error === "invalid_license");
  check("形の違うキーは 401", (await get("/chapter/01", { auth: "Bearer abc" })).status === 401);
  check("Bearer でない形式は 401", (await get("/chapter/01", { auth: license })).status === 401);
  const [pre, pl, sig] = license.split(".");
  const t = pre + "." + pl.slice(0, -1) + (pl.slice(-1) === "A" ? "B" : "A") + "." + sig;
  check("payload 改ざんは 401", (await get("/chapter/01", { auth: "Bearer " + t })).status === 401);
  const foreign = await issueLicense("cs_test_foreign123456", other.priv);
  check("別の鍵で署名したキーは 401", (await get("/chapter/01", { auth: "Bearer " + foreign })).status === 401);
  const pfc = "PFC1." + pl + "." + sig;
  check("PFC1 キーは 401", (await get("/chapter/01", { auth: "Bearer " + pfc })).status === 401);

  const sid = (await verifyLicense(license, main.pub)).sid;
  kv.set("revoked:" + sid, "1");
  const rev = await get("/chapter/01", { auth: "Bearer " + license });
  check("失効したキーは 401", rev.status === 401);
  check("失効時に本文を返さない", !(await rev.text()).includes("第1章"));
  kv.delete("revoked:" + sid);

  check("KV に無い章は 404", (await get("/chapter/02", { auth: "Bearer " + license })).status === 404);
  check("/chapter/13 は 400", (await get("/chapter/13", { auth: "Bearer " + license })).status === 400);
  check("/chapter/1 は 400", (await get("/chapter/1", { auth: "Bearer " + license })).status === 400);
  check("/chapter/00 は 400", (await get("/chapter/00", { auth: "Bearer " + license })).status === 400);
  check("/chapter/01/x は 400", (await get("/chapter/01/x", { auth: "Bearer " + license })).status === 400);

  const bad401 = await get("/chapter/13");
  check("不正な章は認証より先に 400", bad401.status === 400);

  check("LICENSE_PUBLIC_JWK が空なら 500", (await get("/chapter/01", { auth: "Bearer " + license, e: { ...env, LICENSE_PUBLIC_JWK: "" } })).status === 500);
  check("CONTENT が無ければ 500", (await get("/chapter/01", { auth: "Bearer " + license, e: { ...env, CONTENT: undefined } })).status === 500);
}

console.log("[CORS・メソッド]");
{
  const evil = await get("/license?session_id=" + SID, { origin: "https://evil.example" });
  check("許可外 Origin には CORS ヘッダーなし", evil.headers.get("Access-Control-Allow-Origin") === null);
  const opt = await worker.fetch(new Request("https://x.workers.dev/chapter/01", { method: "OPTIONS", headers: { Origin: ORIGIN } }), env);
  check("OPTIONS は 204", opt.status === 204);
  check("Allow-Headers に Authorization", (opt.headers.get("Access-Control-Allow-Headers") || "").includes("Authorization"));
  check("Allow-Methods は GET, OPTIONS", opt.headers.get("Access-Control-Allow-Methods") === "GET, OPTIONS");
  const post = await worker.fetch(new Request("https://x.workers.dev/license?session_id=" + SID, { method: "POST" }), env);
  check("POST は 405", post.status === 405);
  const postCh = await worker.fetch(new Request("https://x.workers.dev/chapter/01", { method: "POST" }), env);
  check("章への POST も 405", postCh.status === 405);
  check("ほかのパスは 404", (await get("/")).status === 404);
}

console.log("");
console.log("結果: " + passed + " passed, " + failed + " failed");
process.exit(failed > 0 ? 1 : 0);
