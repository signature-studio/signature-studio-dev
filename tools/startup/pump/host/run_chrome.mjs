/* run_chrome.mjs — headless Chrome での RING ABI e2e (D 検収と同じ環境でのレイテンシ比較)。
 * 構成: main (producer = worker_pump.ts PumpRing.push の実物) ⇄
 *       Worker (consumer = pump C が memory.atomic.wait32 でブロック) + responder Worker (ctrl 排水)。
 * tools/runtime/lib/{serve,chrome}.mjs を読込のみ利用 (改変しない)。
 */
import { cpSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { serve } from '../../../runtime/lib/serve.mjs';
import { launchChrome } from '../../../runtime/lib/chrome.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WORK = path.resolve(process.argv[2] || path.join(HERE, '..', 'work'));
const CHROME_DIR = path.join(WORK, 'chrome');
const pct = (v) => (typeof v !== 'number' || Number.isNaN(v) ? 'n/a' : v >= 100 ? v.toFixed(0) : v.toFixed(3));

/* ---- stage ---- */
mkdirSync(CHROME_DIR, { recursive: true });
cpSync(path.join(WORK, 'worker_pump.mjs'), path.join(CHROME_DIR, 'worker_pump.mjs'));
cpSync(path.join(HERE, 'responder_browser.mjs'), path.join(CHROME_DIR, 'responder_browser.mjs'));

writeFileSync(path.join(CHROME_DIR, 'pump_worker.mjs'), `\
import PumpMod from './pump_chrome.js';
const mod = await PumpMod();
mod._e2e_setup();
mod._pump_set_wait_mode(0);   // ATOMIC: この Worker 内で C が futex ブロックする
const stats = () => Array.from(new Int32Array(mod.HEAP32.buffer, mod._pump_stats_addr(), 24));
/* 較正検算用: C 生クロック (offset 適用前) を page に渡す */
let cRawAtReady = 0;
self.postMessage({ t: 'ready', sab: mod.HEAP32.buffer, ringAddr: mod._pump_ring_addr(),
  ctrlReq: mod._pump_ctrl_req_addr(), ctrlResp: mod._pump_ctrl_resp_addr(),
  logAddr: mod._pump_pop_log_addr(), cRaw: (cRawAtReady = mod._pump_now_raw()) });
self.onmessage = ({ data }) => {
  if (data.t === 'sync') { self.postMessage({ t: 'sync', c1: mod._pump_now_raw() }); return; }
  if (data.t !== 'go') return;
  if (typeof data.offsetFix === 'number') mod._pump_set_clock_offset(data.offsetFix);  // page 駆動較正 (ctrl 較正より正確)
  mod._pump_calibrate();                       // (offset 済なら skip。ctrl 経由の機能確認を兼ねる)
  mod._e2e_setup_timer(0, 7, 10, 0);
  const runOk = mod._e2e_consumer_run(30000);  // GetMessageW ループ (WM_QUIT まで)
  self.postMessage({ t: 'done', runOk, logN: mod._pump_pop_log_count(), stats: stats(),
    offset: mod._pump_clock_offset(), calibrated: mod._pump_clock_calibrated(),
    cRawAtDone: mod._pump_now_raw() });
};
`);

writeFileSync(path.join(CHROME_DIR, 'index.html'), `\
<!doctype html><meta charset="utf-8"><title>pump chrome e2e</title>
<script type="module">
import { PumpRing, WM } from './worker_pump.mjs';
const N = 300, PACE = 1;
const worker = new Worker('./pump_worker.mjs', { type: 'module' });
const epoch = () => performance.timeOrigin + performance.now();
const cfg = await new Promise((res) => { worker.onmessage = (e) => e.data.t === 'ready' && res(e.data); });
const i32 = new Int32Array(cfg.sab), f64 = new Float64Array(cfg.sab);
const cRawAtReady = cfg.cRaw, pageEpochAtReady = epoch();

// ctrl responder (ネスト Worker): C が書いた要求を排水して戻す
const resp = new Worker('./responder_browser.mjs', { type: 'module' });
resp.postMessage({ t: 'init', sab: cfg.sab, reqAddr: cfg.ctrlReq, respAddr: cfg.ctrlResp });
await new Promise((res) => { resp.onmessage = (e) => e.data.t === 'ready' && res(); });

// 正確な時計較正 (page 駆動 ping-pong): C 生クロックとの往復中点で offset を出し、worker へ設定する。
// ctrl 経由較正はレスポンダ排水粒度 (~RTT/2) の誤差を持つため、計測用にはこちらを使う。
const offsetFix = await new Promise((res) => {
  const t1 = epoch();
  worker.onmessage = ({ data }) => { if (data.t === 'sync') res((t1 + epoch()) / 2 - data.c1); };
  worker.postMessage({ t: 'sync' });
});

// done ハンドラを先に張る (worker の完了メッセージ取りこぼし防止)
worker.onmessage = ({ data }) => {
  if (data.t !== 'done') return;
  // 較正残差: (page epoch - C 生クロック) の ready/done 2 时点と offset の整合を見る
  const rawDeltaReady = pageEpochAtReady - cRawAtReady;
  const rawDeltaDone = epoch() - data.cRawAtDone;
  // pop ログ (24B/件: f64 tPop, f64 tPost, u32 msg, u32 aux) を共有メモリから読む
  const f0 = cfg.logAddr / 8, w0 = cfg.logAddr >> 2, n = data.logN;
  const lat = [];
  let timers = 0;
  for (let i = 0; i < n; i++) {
    const tPop = f64[f0 + i * 3], tPost = f64[f0 + i * 3 + 1];
    const msg = i32[w0 + i * 6 + 4] >>> 0;
    if (msg === 0x0113) timers++;
    else if (tPost > 0) lat.push(tPop - tPost);
  }
  lat.sort((a, b) => a - b);
  const q = (p) => (lat.length ? lat[Math.min(lat.length - 1, Math.floor(lat.length * p))] : NaN);
  const s = data.stats;
  window.__pumpResult = {
    sent, received: s[0], timers, timersFired: s[5],
    waitsAtomic: s[7], dropped: i32[(cfg.ringAddr >> 2) + 5] >>> 0,
    runOk: data.runOk, calibrated: data.calibrated, offset: data.offset,
    clock: { rawDeltaReady, rawDeltaDone, offsetVsRawReady: data.offset - rawDeltaReady },
    lat: { n: lat.length, p50: q(0.5), p90: q(0.9), p99: q(0.99), max: lat[lat.length - 1] ?? NaN },
  };
  window.__pumpDone = true;
};

const ring = new PumpRing(cfg.sab, cfg.ringAddr);
worker.postMessage({ t: 'go', offsetFix });
await new Promise((r) => setTimeout(r, 20));   // 較正完了を待ってから計測開始 (遅延統計を混ぜない)

let sent = 0, stopQueued = false;
const t0 = performance.now();
while (performance.now() - t0 < 30000 && !window.__pumpDone) {
  if (sent < N) { if (ring.push({ message: WM.MOUSEMOVE, ptx: sent, pty: sent, tPost: epoch() })) sent++; }
  else if (!stopQueued) stopQueued = ring.push({ message: WM.APP_RUNTIME_STOP, tPost: epoch() });
  else break;   // STOP 投入済み — worker 側の締めを待つ (done ハンドラで結果を置く)
  await new Promise((r) => setTimeout(r, PACE));
}
</script>
`);

/* ---- Chrome 起動と検証 ---- */
const srv = await serve([{ prefix: '/pump/', dir: CHROME_DIR }], { port: 0 });
let chrome = null;
for (let i = 0; i < 3 && !chrome; i++) {
  try { chrome = await launchChrome(); } catch { await new Promise((r) => setTimeout(r, 1500)); }
}
let fails = 0, checks = 0;
const ok = (c, label, detail) => { checks++; if (!c) { fails++; console.log(`  FAIL: ${label}${detail ? ` — ${detail}` : ''}`); } return !!c; };
try {
    const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/pump/index.html`);
    await page.waitForExpr('window.__pumpDone === true', 60000);
    const result = await page.evaluate('window.__pumpResult');
    const lat = result.lat;
    ok(result.runOk === 1, `Chrome: コンシューマが WM_QUIT で正常終了 (runOk=${result.runOk})`);
    ok(result.received >= 300, `Chrome: 受信 ${result.received} >= 300`);
    ok(result.timers >= 3, `Chrome: WM_TIMER 発火 ${result.timers} (>=3)`);
    ok(result.dropped === 0, `Chrome: 欠落 ${result.dropped}`);
    ok(result.waitsAtomic > 0, `Chrome: 実ブロッキング wait (waits_atomic=${result.waitsAtomic})`);
    ok(lat.p50 < 1.0, `Chrome: p50 ${pct(lat.p50)}ms < 1ms (D 検収 0.01ms との比較は REPORT)`);
    console.log(`  Chrome: n=${lat.n} p50=${pct(lat.p50)}ms p90=${pct(lat.p90)}ms p99=${pct(lat.p99)}ms max=${pct(lat.max)}ms | timers=${result.timers} waits=${result.waitsAtomic} dropped=${result.dropped}`);
    console.log(`  clock: offset=${result.offset?.toFixed(2)}ms calibrated=${result.calibrated} offsetVsRawReady=${result.clock?.offsetVsRawReady?.toFixed(2)}ms (0 に近いほど較正正確)`);
    writeFileSync(path.join(WORK, 'chrome_summary.json'), JSON.stringify(result, null, 1));
} finally {
    await chrome.close();
    await srv.close();
}
console.log(`\nCHROME e2e: ${fails === 0 ? 'ALL PASS' : 'FAILED'} (checks=${checks}, fails=${fails})`);
process.exit(fails === 0 ? 0 : 1);
