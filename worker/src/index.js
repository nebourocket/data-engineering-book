// データエンジニアリング本 — ライセンス発行・応用編配信 Worker (Cloudflare Workers)
//
// やることは 2 つです。
//   1. GET /license?session_id=cs_... … Stripe に「500 円の支払い済みか」を問い合わせ、
//      そうであれば署名付きライセンスキーを返します。
//   2. GET /chapter/01 〜 /chapter/12 … Authorization: Bearer <キー> が有効 (署名が正しく、
//      失効していない) なときだけ、Workers KV に置いた応用編の本文 (HTML) を返します。
//
// カード番号などの決済情報は、この Worker にも本のサイトにも一切届きません
// (入力されるのは Stripe のページだけです)。
//
// 必要な設定 (wrangler.toml と wrangler secret):
//   STRIPE_SECRET_KEY   … 制限付きキー (Checkout Sessions の読み取りのみ) を推奨 (secret)
//   LICENSE_PRIVATE_JWK … ライセンス署名用の秘密鍵 (scripts/gen-keys.mjs で作成) (secret)
//   LICENSE_PUBLIC_JWK  … 上と対の公開鍵 (JSON 文字列)。章の配信でキーの検証に使います
//   ALLOWED_ORIGIN      … 本のサイトの公開元 (例: https://nebourocket.github.io)
//   PRICE_JPY           … 価格 (円)。支払額がこれと一致したときだけ発行します
//   PAYMENT_LINK_ID     … plink_... 。この Payment Link 経由の支払いだけを認めます (空なら発行しません)
//   CONTENT             … 応用編の本文を入れた KV (キーは "chapter:01" 〜 "chapter:12")。
//                         失効したキーは "revoked:<sid>" に何か値を入れると使えなくなります

const SESSION_ID_RE = /^cs_(live|test)_[A-Za-z0-9]{10,250}$/;
const CHAPTER_RE = /^\/chapter\/(0[1-9]|1[0-2])$/;
const LICENSE_PREFIX = "DEB1";

function base64url(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// base64url の復号。壊れていれば例外を投げます (呼び出し側で捕まえます)。
function fromBase64url(text) {
  if (!/^[A-Za-z0-9_-]*$/.test(text)) throw new Error("bad_base64url");
  const b64 = text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

// 鍵の読み込みは重いので、同じ isolate の中では使い回します。
let cachedKey = null;
let cachedJwk = null;
async function signingKey(jwkText) {
  if (cachedKey && cachedJwk === jwkText) return cachedKey;
  const jwk = JSON.parse(jwkText);
  cachedKey = await crypto.subtle.importKey(
    "jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  cachedJwk = jwkText;
  return cachedKey;
}

let cachedPublicKey = null;
let cachedPublicJwk = null;
async function verifyingKey(jwkText) {
  if (cachedPublicKey && cachedPublicJwk === jwkText) return cachedPublicKey;
  const jwk = JSON.parse(jwkText);
  cachedPublicKey = await crypto.subtle.importKey(
    "jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]);
  cachedPublicJwk = jwkText;
  return cachedPublicKey;
}

// ライセンスキー = "DEB1.<payload>.<署名>" (どちらも base64url)。
// payload には個人情報 (メールアドレス等) を入れず、Session ID のハッシュと発行時刻だけを入れます。
export async function issueLicense(sessionId, jwkText, now) {
  const payload = {
    v: 1,
    sid: (await sha256Hex(sessionId)).slice(0, 32),
    iat: Math.floor((now || Date.now()) / 1000),
  };
  const body = base64url(new TextEncoder().encode(JSON.stringify(payload)));
  const signed = LICENSE_PREFIX + "." + body;
  const key = await signingKey(jwkText);
  const sig = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" }, key, new TextEncoder().encode(signed));
  return signed + "." + base64url(new Uint8Array(sig));
}

// ライセンスキーの形・署名・バージョンを確かめます。何が起きても例外は投げず、不正なら null を返します。
export async function verifyLicense(license, publicJwkText) {
  try {
    if (typeof license !== "string") return null;
    const parts = license.split(".");
    if (parts.length !== 3 || parts[0] !== LICENSE_PREFIX) return null;
    const [prefix, body, sigText] = parts;
    const key = await verifyingKey(publicJwkText);
    const ok = await crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" }, key, fromBase64url(sigText),
      new TextEncoder().encode(prefix + "." + body));
    if (!ok) return null;
    const payload = JSON.parse(new TextDecoder().decode(fromBase64url(body)));
    if (!payload || payload.v !== 1 || typeof payload.sid !== "string" || typeof payload.iat !== "number") {
      return null;
    }
    return { v: 1, sid: payload.sid, iat: payload.iat };
  } catch (e) {
    return null;
  }
}

function corsHeaders(env, request) {
  const origin = request.headers.get("Origin");
  const headers = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Vary": "Origin",
  };
  if (origin && origin === env.ALLOWED_ORIGIN) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Methods"] = "GET, OPTIONS";
    headers["Access-Control-Allow-Headers"] = "Authorization";
    headers["Access-Control-Max-Age"] = "86400";
  }
  return headers;
}

function reply(env, request, status, obj) {
  return new Response(JSON.stringify(obj), { status, headers: corsHeaders(env, request) });
}

// Stripe の Checkout Session が、この商品の支払い済みかを確かめます。
export function isPaidSession(session, env) {
  if (!session || typeof session !== "object") return false;
  if (session.object !== "checkout.session") return false;
  if (session.mode !== "payment") return false;
  if (session.status !== "complete") return false;
  if (session.payment_status !== "paid") return false;
  if (session.currency !== "jpy") return false;
  if (session.amount_total !== Number(env.PRICE_JPY)) return false;
  if (!env.PAYMENT_LINK_ID || session.payment_link !== env.PAYMENT_LINK_ID) return false;
  return true;
}

async function handleLicense(request, env, url) {
  const sessionId = url.searchParams.get("session_id") || "";
  if (!SESSION_ID_RE.test(sessionId)) {
    return reply(env, request, 400, { error: "bad_session_id" });
  }
  if (!env.STRIPE_SECRET_KEY || !env.LICENSE_PRIVATE_JWK || !env.PRICE_JPY || !env.PAYMENT_LINK_ID) {
    return reply(env, request, 500, { error: "not_configured" });
  }

  let res;
  try {
    res = await fetch(
      "https://api.stripe.com/v1/checkout/sessions/" + encodeURIComponent(sessionId),
      { headers: { Authorization: "Bearer " + env.STRIPE_SECRET_KEY } });
  } catch (e) {
    return reply(env, request, 502, { error: "stripe_unreachable" });
  }
  // Stripe からのエラー内容はそのまま返さず、種類だけを伝えます。
  if (res.status === 404) return reply(env, request, 404, { error: "session_not_found" });
  if (!res.ok) return reply(env, request, 502, { error: "stripe_error" });

  let session;
  try {
    session = await res.json();
  } catch (e) {
    return reply(env, request, 502, { error: "stripe_error" });
  }
  if (!isPaidSession(session, env)) {
    return reply(env, request, 402, { error: "not_paid" });
  }

  let license;
  try {
    license = await issueLicense(sessionId, env.LICENSE_PRIVATE_JWK);
  } catch (e) {
    return reply(env, request, 500, { error: "not_configured" });
  }
  return reply(env, request, 200, { license });
}

// 応用編の章を返します。有効なキー (署名が正しく、失効していない) のときだけ本文を渡します。
async function handleChapter(request, env, url) {
  const m = CHAPTER_RE.exec(url.pathname);
  if (!m) return reply(env, request, 400, { error: "bad_chapter" });
  if (!env.LICENSE_PUBLIC_JWK || !env.CONTENT) {
    return reply(env, request, 500, { error: "not_configured" });
  }

  const auth = request.headers.get("Authorization") || "";
  const bearer = /^Bearer\s+(.+)$/i.exec(auth.trim());
  const payload = bearer ? await verifyLicense(bearer[1].trim(), env.LICENSE_PUBLIC_JWK) : null;
  if (!payload) return reply(env, request, 401, { error: "invalid_license" });

  let revoked;
  let body;
  try {
    revoked = await env.CONTENT.get("revoked:" + payload.sid);
    if (revoked === null || revoked === undefined) body = await env.CONTENT.get("chapter:" + m[1]);
  } catch (e) {
    return reply(env, request, 500, { error: "not_configured" });
  }
  if (revoked !== null && revoked !== undefined) {
    return reply(env, request, 401, { error: "invalid_license" });
  }
  if (body === null || body === undefined) {
    return reply(env, request, 404, { error: "chapter_not_found" });
  }

  const headers = corsHeaders(env, request);
  headers["Content-Type"] = "text/html; charset=utf-8";
  headers["Cache-Control"] = "private, no-store";
  return new Response(body, { status: 200, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(env, request) });
    }
    const isLicense = url.pathname === "/license";
    const isChapter = url.pathname.startsWith("/chapter/");
    if (!isLicense && !isChapter) {
      return reply(env, request, 404, { error: "not_found" });
    }
    if (request.method !== "GET") {
      return reply(env, request, 405, { error: "method_not_allowed" });
    }
    return isLicense ? handleLicense(request, env, url) : handleChapter(request, env, url);
  },
};
