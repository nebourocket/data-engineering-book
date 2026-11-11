// 応用編の購入ボタン・キー表示・本文の読み込みを行います。
import { normalizeLicense, sessionIdFromUrl, stripSessionId, makeStore, chapterState, licenseOutcome } from "./pro-core.js";

const MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";
const cfg = window.DE_BOOK_CONFIG || {};
const base = (cfg.licenseApiBase || "").replace(/\/+$/, "");
const payUrl = cfg.paymentLinkUrl || "";
const ready = Boolean(base && payUrl);

let store;
try { store = makeStore(window.localStorage); } catch { store = makeStore({}); }

// 文言はすべて textContent で入れます。
function el(tag, text, attrs = {}) {
  const e = document.createElement(tag);
  if (text) e.textContent = text;
  Object.assign(e, attrs);
  return e;
}

function note(text) { return el("p", text, { className: "pro-note" }); }

function buyBlock(onKey) {
  const box = el("div", null, { className: "pro-buy-box" });
  const a = el("a", "500円で応用編を買う (買い切り)", { href: payUrl, className: "md-button md-button--primary" });
  box.append(a, pasteForm(onKey));
  return box;
}

function pasteForm(onKey) {
  const form = el("form", null, { className: "pro-paste" });
  const label = el("label", "購入済みの方はキーを貼り付けてください");
  const input = el("input", null, { type: "text", autocomplete: "off", spellcheck: false });
  input.setAttribute("aria-label", "ライセンスキー");
  const btn = el("button", "キーを使う", { type: "submit" });
  const msg = el("p", null, { className: "pro-note" });
  form.append(label, input, btn, msg);
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const key = normalizeLicense(input.value);
    if (!key) { msg.textContent = "キーの形が正しくありません。もう一度貼り付けてください。"; return; }
    store.set(key);
    onKey(key);
  });
  return form;
}

function keyBlock(key) {
  const box = el("div", null, { className: "pro-key" });
  const label = el("label", "あなたのキー (別の端末で使うときに貼り付けます)");
  const input = el("input", null, { type: "text", readOnly: true, value: key });
  const copy = el("button", "コピー", { type: "button" });
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(key); copy.textContent = "コピーしました"; }
    catch { input.select(); }
  });
  box.append(label, input, copy);
  return box;
}

// 戻り値は { outcome, key }。通信失敗は status null として扱います。
async function fetchLicense(sessionId) {
  let status = null;
  try {
    const res = await fetch(`${base}/license?session_id=${encodeURIComponent(sessionId)}`);
    status = res.status;
    if (status === 200) {
      const key = normalizeLicense((await res.json()).license);
      return key ? { outcome: "ok", key } : { outcome: "failed", key: null };
    }
  } catch {
    status = null;
  }
  return { outcome: licenseOutcome(status), key: null };
}

async function renderMermaid(root) {
  const nodes = root.querySelectorAll("pre.mermaid");
  if (!nodes.length) return;
  const mod = await import(MERMAID_URL);
  const mermaid = mod.default;
  mermaid.initialize({ startOnLoad: false });
  const list = Array.from(nodes);
  // KV の HTML は <pre class="mermaid"><code>…</code></pre> なので、mermaid が読めるよう素のテキストにします。
  list.forEach((n) => { n.textContent = n.textContent; });
  try {
    await mermaid.run({ nodes: list });
  } catch (e) {
    console.warn("Mermaid の描画に失敗しました", e);
  }
}

async function loadChapter(div, key) {
  const id = div.dataset.chapter;
  div.replaceChildren(note("読み込み中です…"));
  let res;
  try {
    res = await fetch(`${base}/chapter/${encodeURIComponent(id)}`, { headers: { Authorization: `Bearer ${key}` } });
  } catch {
    div.replaceChildren(note("読み込めませんでした。通信を確かめて、もう一度開いてください。"));
    return;
  }
  const state = chapterState(res.status);
  if (state === "ok") {
    let html;
    try { html = await res.text(); } catch {
      div.replaceChildren(note("読み込めませんでした。通信を確かめて、もう一度開いてください。"));
      return;
    }
    // 自分の Worker から届く信頼できる HTML なので innerHTML で入れます。
    div.innerHTML = html;
    await renderMermaid(div).catch(() => {});
  } else if (state === "invalid") {
    store.clear();
    div.replaceChildren(note("このキーは使えません。"), buyBlock((k) => useKey(k)));
  } else if (state === "missing") {
    div.replaceChildren(note("この章は準備中です"));
  } else {
    div.replaceChildren(note("読み込めませんでした。時間をおいてもう一度開いてください。"));
  }
}

let buyBox = null;
let chapterDivs = [];
let statusNote = null;

// キーの有無に合わせて、購入欄と各章を描き直します (再読み込みはしません)。
async function render() {
  const key = store.get();
  if (buyBox) {
    buyBox.replaceChildren();
    if (statusNote) buyBox.append(statusNote);
    buyBox.append(key ? keyBlock(key) : buyBlock(useKey));
  }
  for (const div of chapterDivs) {
    if (key) await loadChapter(div, key);
    else div.replaceChildren(buyBlock(useKey));
  }
}

function useKey(key) {
  store.set(key);
  statusNote = null;
  return render();
}

async function main() {
  buyBox = document.querySelector(".pro-buy");
  chapterDivs = Array.from(document.querySelectorAll(".pro-chapter"));
  if (!buyBox && !chapterDivs.length) return;

  if (!ready) {
    for (const t of [buyBox, ...chapterDivs]) if (t) t.replaceChildren(note("応用編は準備中です"));
    return;
  }

  // 支払い直後は session_id からキーを受け取ります。再試行できる失敗では URL に残します。
  const sid = sessionIdFromUrl(location.href);
  if (sid) {
    const { outcome, key } = await fetchLicense(sid);
    if (outcome === "ok") store.set(key);
    else if (outcome === "failed") statusNote = note("支払いを確認できませんでした。お問い合わせください");
    else statusNote = note("支払いの確認に失敗しました。このページをもう一度読み込んでください");
    if (outcome !== "retry") history.replaceState(null, "", stripSessionId(location.href));
  }
  await render();
}

main().catch(() => {
  for (const t of [buyBox, ...chapterDivs]) if (t) t.replaceChildren(note("読み込めませんでした。時間をおいてもう一度開いてください。"));
});
