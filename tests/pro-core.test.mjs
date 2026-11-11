// pro-core.js のテスト (DOM は使いません)
// 実行: node tests/pro-core.test.mjs
import { normalizeLicense, sessionIdFromUrl, stripSessionId, makeStore, chapterState, licenseOutcome } from "../book/assets/pro-core.js";

let failed = 0;
function check(name, cond) {
  if (cond) console.log("  ok - " + name);
  else { failed += 1; console.log("  NG - " + name); }
}

check("normalize: 空白と改行を除く", normalizeLicense("  DEB1.ab.cd\n") === "DEB1.ab.cd");
check("normalize: 途中の改行も除く", normalizeLicense("DEB1.ab\n.cd") === "DEB1.ab.cd");
check("normalize: PFC1 は拒否", normalizeLicense("PFC1.ab.cd") === null);
check("normalize: 2 区切りは拒否", normalizeLicense("DEB1.ab") === null);
check("normalize: 空は拒否", normalizeLicense("") === null);

check("session: 取り出す", sessionIdFromUrl("https://x.test/advanced/?session_id=cs_test_x") === "cs_test_x");
check("session: 無ければ null", sessionIdFromUrl("https://x.test/advanced/") === null);
check("strip: 他のクエリと hash を残す",
  stripSessionId("https://x.test/advanced/?a=1&session_id=cs_x&b=2#top") === "https://x.test/advanced/?a=1&b=2#top");
check("strip: 唯一のクエリなら ? も消す", stripSessionId("https://x.test/advanced/?session_id=cs_x") === "https://x.test/advanced/");

const broken = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); }, removeItem() { throw new Error("denied"); } };
const s = makeStore(broken);
s.set("k");
check("store: storage が壊れてもメモリで持つ", s.get() === "k");
s.clear();
check("store: clear 後は null", s.get() === null);
const m = new Map();
const ok = makeStore({ getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) });
ok.set("v");
check("store: 通常の storage に保存", m.get("deb-license") === "v" && ok.get() === "v");

check("chapterState 200", chapterState(200) === "ok");
check("chapterState 401", chapterState(401) === "invalid");
check("chapterState 404", chapterState(404) === "missing");
check("chapterState 500", chapterState(500) === "error");

check("licenseOutcome 200", licenseOutcome(200) === "ok");
check("licenseOutcome 400/402/404", [400, 402, 404].every((c) => licenseOutcome(c) === "failed"));
check("licenseOutcome 500/502", licenseOutcome(500) === "retry" && licenseOutcome(502) === "retry");
check("licenseOutcome null (通信失敗)", licenseOutcome(null) === "retry");

if (failed) { console.log(failed + " failed"); process.exit(1); }
console.log("all passed");
