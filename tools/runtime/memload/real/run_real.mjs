#!/usr/bin/env node
// RT-6 実 loader 試験 (#125) 1 コマンド: `node tools/runtime/memload/real/run_real.mjs [--neg-only|--pos-only]`
// PluginPool を hostbridge の loader (host_vst2.wasm + 共有 hb_bridge.mjs) に接続し、lowbase 版 OTT を
// 150 種 + 320 pin で回す。各ケースは新しい headless Chrome (= 新しいレンダラ)。判定が崩れたら exit 1。
// ネガティブコントロール (NEG) は「壊すと OOM / 判定 FAIL になる」ことを確認し、検出しなければ exit 1。
// 前提: bash tools/hostbridge/lowbase/retdec/build_m10_lb.sh (lowbase 版 OTT) と retdec/build_host_lb.sh (host_vst2.wasm)。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { serve } from "../../lib/serve.mjs";
import { launchChrome } from "../../lib/chrome.mjs";
import { transpile } from "../transpile.mjs";

process.removeAllListeners("warning");
const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../../..");
const LB = path.join(ROOT, "tools/hostbridge/lowbase/work");
const SRC = {
  "ott_hb.cjs": path.join(LB, "m10_0x10000/ott_hb.cjs"),
  "ott_hb.wasm": path.join(LB, "m10_0x10000/ott_hb.wasm"),
  "host_vst2.wasm": path.join(LB, "host_vst2.wasm"),
  "hb_bridge.mjs": path.join(ROOT, "tools/hostbridge/poc/hb_bridge.mjs"),
  "real_worker.mjs": path.join(here, "real_worker.mjs"),
};
const mode = process.argv.includes("--neg-only") ? "neg" : process.argv.includes("--pos-only") ? "pos" : "all";

for (const [name, p] of Object.entries(SRC)) {
  if (!fs.existsSync(p)) { console.error(`前提無し: ${p} (${name})。先に lowbase のビルドを実行`); process.exit(2); }
}
const STAGE = path.join(here, "work", "real_stage");
fs.rmSync(STAGE, { recursive: true, force: true });
fs.mkdirSync(STAGE, { recursive: true });
for (const [name, p] of Object.entries(SRC)) fs.copyFileSync(p, path.join(STAGE, name));
fs.copyFileSync(transpile(), path.join(STAGE, "memory_budget.js"));
fs.writeFileSync(path.join(STAGE, "index.html"), `<!doctype html><meta charset="utf-8"><title>RT-6 real loader</title><script>
const mode = location.hash.slice(1);
const w = new Worker("real_worker.mjs", { type: "module" });
w.onmessage = (e) => { window.__r = e.data; };
w.onerror = (e) => { window.__r = { mode, fatal: true, err: { name: "worker-error", message: String(e.message) } }; };
w.postMessage({ mode });
</script>
`);

const NATIVE_LIMIT = 124; // tools/runtime/REPORT.md RT-6 の実測 (wasm32 Memory 個数上限)
const NPLUG = 150, PINS = 150 + 170;
const isOom = (e) => !!e && /could not allocate memory|Out of memory/i.test(e.message ?? "");

const checks = {
  pos: (r) => {
    const f = [];
    if (r.fatal || r.err) f.push(`例外 ${JSON.stringify(r.err)} (ロード ${r.loads} 回目)`);
    if (r.pins !== PINS) f.push(`pins=${r.pins} != ${PINS}`);
    if (r.loads <= NATIVE_LIMIT) f.push(`累計ロード ${r.loads} がネイティブ上限 ${NATIVE_LIMIT} を超えていない (追い出しが効いていない)`);
    if (r.loads !== r.evictions + r.finalSize) f.push(`loads(${r.loads}) != evictions(${r.evictions}) + 生存(${r.finalSize}) (追い出し以外で entry が消えた/残った)`);
    if (r.peakSize > r.cap || r.peakInUse > r.cap) f.push(`予算超過 peakSize=${r.peakSize} peakInUse=${r.peakInUse} cap=${r.cap}`);
    if (r.finalInUse !== r.finalSize) f.push(`枠と entry の不一致 inUse=${r.finalInUse} size=${r.finalSize}`);
    if (r.coldLoads !== r.loads) f.push(`cold 照合 ${r.coldLoads} 件 != ロード ${r.loads} 件 (照合されていないロードがある)`);
    if (r.hashMismatch !== 0) f.push(`cold ロード直後の出力 sha256 が基準と不一致 ${r.hashMismatch} 件 (基準 ${r.refHash?.slice(0, 16)})`);
    if (r.paramMismatch) f.push(`warm pin で param 読み戻しが不一致 ${r.paramMismatch} 件 (instance の状態喪失疑い)`);
    if (r.handleMismatch !== 0) f.push(`hostbridge の handle と pool の対応が崩れた ${r.handleMismatch} 件`);
    if (!r.refHash) f.push("出力 sha256 の基準が無い");
    if (r.bridgeLoaded !== r.finalSize || r.bridgeHandles !== r.bridgeLoaded) f.push(`bridge の登録数 ${r.bridgeLoaded} / 一意 handle ${r.bridgeHandles} が生存 entry ${r.finalSize} と一致しない`);
    if (r.afterUnloadSize !== 0 || r.afterUnloadInUse !== 0 || r.afterUnloadBridge !== 0) f.push(`全解放後に参照が残った size=${r.afterUnloadSize} inUse=${r.afterUnloadInUse} bridge=${r.afterUnloadBridge}`);
    return f;
  },
  // 負: cap が実測上限を超えると、追い出しが効いていても Memory 生成が OOM になる (予算値 96 の必要性)
  neg_cap: (r) => (isOom(r.err) && r.atLoad >= NATIVE_LIMIT - 4 && r.atLoad <= 130 ? [] : [`OOM が ${NATIVE_LIMIT - 4}〜130 ロードの間で出ない: ${JSON.stringify(r.err)} atLoad=${r.atLoad}`]),
  // 負: dispose で FreeLibrary を呼ばないと bridge が Memory を握り続け、pool の追い出しに関係なく上限で OOM になる
  neg_nofree: (r) => (isOom(r.err) && r.atLoad >= NATIVE_LIMIT - 8 && r.atLoad <= NATIVE_LIMIT + 4 ? [] : [`OOM が ${NATIVE_LIMIT - 8}〜${NATIVE_LIMIT + 4} ロードの間で出ない: ${JSON.stringify(r.err)} atLoad=${r.atLoad}`]),
};
const cases = [
  ["pos", "pos", "real_pool"],
  ["neg", "neg_cap", "neg_cap130"],
  ["neg", "neg_nofree", "neg_nofree"],
].filter(([kind]) => mode === "all" || mode === kind);

const srv = await serve([{ prefix: "/", dir: STAGE }]);
let fail = 0;
try {
  for (const [kind, m, name] of cases) {
    const t0 = Date.now();
    const chrome = await launchChrome();
    let r;
    try {
      const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/index.html#${m}`);
      r = await page.waitForExpr("window.__r", 900000);
      const sec = (Date.now() - t0) / 1000;
      const { loads, pins, evictions, finalSize, peakSize, peakInUse, refHash, err, atLoad, sec: caseSec } = r;
      console.log(`INFO [${name}] chrome ${chrome.version} total ${sec.toFixed(1)}s run ${caseSec?.toFixed?.(2) ?? "-"}s pins=${pins} loads=${loads} evictions=${evictions} live=${finalSize} peakSize=${peakSize} peakInUse=${peakInUse} ref=${refHash?.slice(0, 16) ?? "-"} err=${err ? JSON.stringify(err) : "none"} atLoad=${atLoad}`);
      if (page.exceptions?.length) console.log(`INFO [${name}] page exceptions: ${JSON.stringify(page.exceptions).slice(0, 300)}`);
    } finally { await chrome.close(); }
    const f = checks[kind === "pos" ? "pos" : m](r);
    if (kind === "pos") {
      if (f.length) { fail++; console.log(`FAIL [${name}] ${f.join(" | ")}`); }
      else console.log(`PASS [${name}] 全判定 OK`);
    } else {
      if (f.length) { fail++; console.log(`NEG-MISS [${name}] 壊した条件で検出されなかった: ${f.join(" | ")}`); }
      else console.log(`NEG-OK [${name}] 検出 (${r.err?.message?.slice(0, 80)} at load ${r.atLoad})`);
    }
  }
} finally { await srv.close(); }
console.log(fail === 0 ? "ALL PASS" : `FAIL ${fail}`);
process.exit(fail === 0 ? 0 : 1);
