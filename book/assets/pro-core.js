// 応用編の購入・キー処理の純粋な部分です (DOM には触れません)。
const LICENSE_RE = /^DEB1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
export const STORAGE_KEY = "deb-license";

// 空白と改行を除き、キーの形ならそのまま返します。
export function normalizeLicense(text) {
  const t = String(text ?? "").replace(/\s+/g, "");
  return LICENSE_RE.test(t) ? t : null;
}

export function sessionIdFromUrl(href) {
  const id = new URL(href).searchParams.get("session_id");
  return id || null;
}

// session_id だけを消し、ほかのクエリと #hash は残します。
export function stripSessionId(href) {
  const u = new URL(href);
  u.searchParams.delete("session_id");
  return u.toString();
}

// storage が使えない環境 (プライベートモードなど) でもメモリで動きます。
export function makeStore(storage) {
  let mem = null;
  return {
    get() {
      try {
        const v = storage.getItem(STORAGE_KEY);
        if (v) return v;
      } catch { /* メモリの値を使う */ }
      return mem;
    },
    set(v) {
      mem = v;
      try { storage.setItem(STORAGE_KEY, v); } catch { /* メモリだけで持つ */ }
    },
    clear() {
      mem = null;
      try { storage.removeItem(STORAGE_KEY); } catch { /* 無視 */ }
    },
  };
}

export function chapterState(status) {
  if (status === 200) return "ok";
  if (status === 401) return "invalid";
  if (status === 404) return "missing";
  return "error";
}

// /license の結果: 200 は成功、400/402/404 は支払いを確認できない、5xx と通信失敗は再試行できる。
export function licenseOutcome(status) {
  if (status === 200) return "ok";
  if (status === 400 || status === 402 || status === 404) return "failed";
  return "retry";
}
