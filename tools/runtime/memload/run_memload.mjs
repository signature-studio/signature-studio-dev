#!/usr/bin/env node
// RT-6 負荷試験: 1 コマンド `node tools/runtime/memload/run_memload.mjs [--neg-only|--pos-only]`
// 各ケースを新しい headless Chrome (= 新しいレンダラ) で実行し、判定が崩れたら exit 1。
// ネガティブコントロール (NEG) は「壊した入力で判定が FAIL する」ことを確認し、FAIL しなければ exit 1。
import path from "node:path";
import { fileURLToPath } from "node:url";
import os from "node:os";
import { serve } from "../lib/serve.mjs";
import { launchChrome } from "../lib/chrome.mjs";
import { transpile, genDir } from "./transpile.mjs";

process.removeAllListeners("warning");
const here = path.dirname(fileURLToPath(import.meta.url));
const mode = process.argv.includes("--neg-only") ? "neg" : process.argv.includes("--pos-only") ? "pos" : "all";
transpile();

const NATIVE_LIMIT = 124; // tools/runtime/REPORT.md RT-6 の実測 (wasm32)
const isOom = (e) => !!e && /could not allocate memory|Out of memory/i.test(e.message ?? "");

// 各 check は失敗理由の配列を返す (空 = PASS)
const checks = {
  naive: (r) => {
    const f = [];
    if (r.err == null) f.push(`無予算なのに上限に達しなかった (created=${r.created})`);
    else if (!isOom(r.err)) f.push(`想定外のエラー ${JSON.stringify(r.err)}`);
    if (r.created < NATIVE_LIMIT - 4 || r.created > NATIVE_LIMIT + 4) f.push(`created=${r.created} が実測上限 ${NATIVE_LIMIT}±4 の外`);
    return f;
  },
  pool_churn: (r) => {
    const f = [];
    if (r.err) f.push(`例外 ${JSON.stringify(r.err)}`);
    if (r.pins !== 1500) f.push(`pins=${r.pins} != 1500`);
    if (r.loads <= NATIVE_LIMIT) f.push(`累計ロード ${r.loads} がネイティブ上限 ${NATIVE_LIMIT} を超えていない (追い出しが効いていない)`);
    if (r.evictions < r.loads - r.cap) f.push(`evictions=${r.evictions} < loads-cap=${r.loads - r.cap}`);
    if (r.peakInUse > r.cap || r.peakSize > r.cap) f.push(`予算超過 peakInUse=${r.peakInUse} peakSize=${r.peakSize} cap=${r.cap}`);
    if (r.badState !== 0) f.push(`プラグイン状態不一致 ${r.badState} 件`);
    if (r.finalInUse > r.cap) f.push(`finalInUse=${r.finalInUse} > cap`);
    return f;
  },
  pool_concurrent: (r) => {
    const f = [];
    if (r.err) f.push(`例外 ${JSON.stringify(r.err)}`);
    if (r.pinned !== 120) f.push(`同時 pin=${r.pinned} != 120`);
    if (!r.stateOk) f.push("同時ロードしたプラグインの状態不一致");
    if (r.sizeAfter !== 120 || r.inUseAfter !== 120) f.push(`size=${r.sizeAfter} inUse=${r.inUseAfter} (期待 120)`);
    if (r.over?.name !== "MemoryBudgetExceeded") f.push(`121 本目の拒否が MemoryBudgetExceeded でない: ${JSON.stringify(r.over)}`);
    if (r.afterOverInUse !== 120) f.push(`拒否後に枠がリーク/過剰解放 inUse=${r.afterOverInUse}`);
    if (r.recovered !== true) f.push(`unpin 後の LRU 追い出しで 121 本目が入らない: ${JSON.stringify(r.recovered)}`);
    if (r.evictions !== 1) f.push(`evictions=${r.evictions} != 1`);
    if (r.dedupLoads !== 1) f.push(`同一 id 同時 pin のロード回数=${r.dedupLoads} != 1`);
    return f;
  },
  pool_race: (r) => {
    const f = [];
    const bad = (pred, msg) => { const ks = r.window.filter(pred).map((a) => a.k); if (ks.length) f.push(`${msg} (k=${ks.join(",")})`); };
    bad((a) => !a.aOk, "pin(A) が失敗");
    bad((a) => a.aOk && a.aDisposed, "pin(A) が破棄済みハンドルを返した");
    bad((a) => !a.hasA, "pin 済みの A がプールに居ない");
    bad((a) => a.bOk || a.bErr !== "MemoryBudgetExceeded", "A が pin 済みなのに pin(B) が MemoryBudgetExceeded で拒否されない");
    bad((a) => a.inUse !== 1 || a.size !== 1, "枠と生存エントリが一致しない (期待 inUse=1 size=1)");
    const s = r.stress;
    if (s.otherErr) f.push(`想定外の例外 ${JSON.stringify(s.otherErr)}`);
    if (s.stale !== 0) f.push(`破棄済み/別 id のハンドルを ${s.stale} 件受け取った`);
    if (s.handed < 100 || s.evictions < 20) f.push(`競合が起きる条件になっていない handed=${s.handed} evictions=${s.evictions}`);
    if (s.peakInUse > s.cap) f.push(`予算超過 peakInUse=${s.peakInUse} cap=${s.cap}`);
    if (s.quiescent.live !== s.quiescent.size || s.quiescent.size !== s.quiescent.inUse) f.push(`静止時に 生存 value=${s.quiescent.live} / size=${s.quiescent.size} / inUse=${s.quiescent.inUse} が不一致`);
    if (s.afterDrain.size !== 0 || s.afterDrain.inUse !== 0 || s.afterDrain.live !== 0) f.push(`全 unpin 後に追い出し切れない (pin 数リーク) ${JSON.stringify(s.afterDrain)}`);
    return f;
  },
  create_fail_releases: (r) => {
    const f = [];
    if (r.err?.name !== "RangeError") f.push(`不正 descriptor が RangeError でない: ${JSON.stringify(r.err)}`);
    if (r.inUseWithOk !== 1) f.push(`失敗した予約が返っていない inUse=${r.inUseWithOk} (期待 1)`);
    if (r.inUseAfter !== 0) f.push(`release 後 inUse=${r.inUseAfter} (期待 0 / 二重解放で負数にならないこと)`);
    return f;
  },
  cross_thread: (r) => {
    const f = [];
    if (r.worker.err) f.push(`Worker で例外 ${JSON.stringify(r.worker.err)}`);
    if (r.mainCreated !== 60) f.push(`main=${r.mainCreated} != 60`);
    if (r.worker.created !== 60 || r.worker.deniedAt !== 60) f.push(`Worker created=${r.worker.created} deniedAt=${r.worker.deniedAt} (期待 60/60)`);
    if (r.inUse !== 120) f.push(`共有カウンタ inUse=${r.inUse} != 120`);
    return f;
  },
  wasm64: (r) => {
    const f = [];
    if (r.err) f.push(`例外 ${JSON.stringify(r.err)}`);
    if (r.granted !== 60 || r.denied !== 10) f.push(`granted=${r.granted} denied=${r.denied} (期待 60/10)`);
    if (r.inUse !== 120) f.push(`inUse=${r.inUse} != 120`);
    return f;
  },
};

// [case, query, check, 説明, 負の場合 (neg) に期待する失敗理由の部分文字列]
const POS = [
  ["naive", "", checks.naive, "無予算 300 instance → 実上限で OOM (問題の再現)"],
  ["pool_churn", "", checks.pool_churn, "300 種 × 1500 pin / cap=96"],
  ["pool_concurrent", "", checks.pool_concurrent, "120 同時ロード + 121 本目拒否 + LRU 回復"],
  ["pool_race", "", checks.pool_race, "pin 復帰前の追い出しで破棄済みハンドルを返さない (cap=1 窓 9 通り + 8 枠・24 種の並行 1440 pin)"],
  ["create_fail_releases", "", checks.create_fail_releases, "Memory 生成失敗で予約が戻る"],
  ["cross_thread", "", checks.cross_thread, "main 60 + Worker 60 (共有カウンタ)"],
  ["wasm64", "", checks.wasm64, "wasm64 = 2 slot (cap=120 → 60 本で拒否)"],
];
const NEG = [
  ["pool_churn", "neg=leak", checks.pool_churn, "追い出し後も参照を保持 → Memory 回収されず上限 OOM で FAIL すること", /例外|予算超過|累計/],
  ["pool_churn", "cap=130", checks.pool_churn, "cap をネイティブ上限超 (130) に設定 → OOM で FAIL すること", /例外/],
  ["pool_concurrent", "cap=130", checks.pool_concurrent, "cap=130 / 120 本 → 121 本目が予算拒否でなく OOM / 非拒否になり FAIL すること", /MemoryBudgetExceeded|121 本目/],
  ["wasm64", "cap=140", checks.wasm64, "wasm64 に cap=140 (70 本分 > 実上限 61〜62 本) → RangeError で FAIL すること", /例外/],
  ["pool_race", "neg=legacy", checks.pool_race, "修正前の pin (await 後に pins++) に戻す → 破棄済みハンドルを返して FAIL すること", /破棄済み/],
  ["cross_thread", "budget=0", checks.cross_thread, "Worker が予算を使わない → 合計が上限を超え Worker が RangeError で FAIL すること", /Worker/],
];

let fail = 0;
const out = [];
async function runCase(name, query) {
  const srv = await serve([{ prefix: "/gen/", dir: genDir }, { prefix: "/", dir: here }]);
  const chrome = await launchChrome();
  try {
    const t0 = Date.now();
    const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/index.html?case=${name}${query ? "&" + query : ""}`);
    const r = await page.waitFor("__result", 120000);
    return { r, sec: (Date.now() - t0) / 1000, chrome: chrome.version, exceptions: page.exceptions };
  } finally { await chrome.close(); await srv.close(); }
}

const load0 = os.loadavg()[0].toFixed(2);
const T0 = Date.now();
if (mode !== "neg") {
  for (const [name, query, check, desc] of POS) {
    const { r, sec, chrome } = await runCase(name, query);
    const f = r.fatal ? [`fatal ${JSON.stringify(r.fatal)}`] : check(r);
    const ok = f.length === 0;
    if (!ok) fail++;
    out.push(`${ok ? "PASS" : "FAIL"}  ${name}${query ? "?" + query : ""}  (${sec.toFixed(1)}s, ${chrome})  ${desc}`);
    console.log(out.at(-1)); console.log("      " + JSON.stringify(r));
    if (!ok) for (const x of f) console.log("      ✗ " + x);
  }
}
if (mode !== "pos") {
  for (const [name, query, check, desc, expect] of NEG) {
    const { r, sec } = await runCase(name, query);
    const f = r.fatal ? [`fatal ${JSON.stringify(r.fatal)}`] : check(r);
    const detected = f.length > 0 && f.some((x) => expect.test(x));
    if (!detected) fail++;
    out.push(`${detected ? "NEG-OK" : "NEG-MISSED"}  ${name}?${query}  (${sec.toFixed(1)}s)  ${desc}`);
    console.log(out.at(-1)); console.log("      " + JSON.stringify(r));
    for (const x of f) console.log("      ✗(期待どおり検出) " + x);
  }
}
const total = ((Date.now() - T0) / 1000).toFixed(1);
console.log(`\n${fail === 0 ? "ALL PASS" : `FAILED (${fail})`}  total=${total}s  loadavg(start)=${load0} loadavg(end)=${os.loadavg()[0].toFixed(2)}  nproc=${os.cpus().length}`);
process.exit(fail === 0 ? 0 : 1);
