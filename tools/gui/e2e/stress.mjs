// stress.mjs — 長時間ストレス + リーク検査 (GUI-8 / #184)。ブラウザ操作は tools/e2e/suite/drivers 経由。
//   テスト PE (gui_app) に実マウス down の後、ページ内から pointermove を大量に流し (1 move = 1 WM_MOUSEMOVE = 1 frame)、
//   STRESS_FRAMES (既定 30000) フレーム処理する。STRESS_SAMPLE フレームごとに入力リング drop / out_full_waits / wasm memory /
//   surface gen / memory.buffer identity 変化を採取し、judgeStress() で合否判定 (不合格は exit 1)。
//   最後に実マウス/キーでシナリオを golden と同じ終状態へ収束させ、独立 oracle (golden/gen_golden.py) と画素完全一致を見る。
//   STRESS_FAULT (ネガコン; 不合格になるべき欠陥を故意に注入):
//     burst : 同期的に 200000 move を一気に push → 入力リング drop が出ること
//     leak  : 後半も memory.grow を続ける (要 GUI_WASM_DIR=build/wasm_grow) → 「後半で増加」を検出すること
//   STRESS_GROW=N : 前半に memory.grow(1 page) を N 回 (要 wasm_grow)。worker の memory.buffer 再取得後も描画が続き golden 一致すること
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { BUILD, H, ROOT, W, countPixelDiff, judgeStress, openDriver, readPPM, startServer } from "./e2e_lib.mjs";

const FRAMES = Number(process.env.STRESS_FRAMES || 30000);
const SAMPLE = Number(process.env.STRESS_SAMPLE || 1000);
const FAULT = process.env.STRESS_FAULT || "";
const GROW = Number(process.env.STRESS_GROW || 0);
const SLOW_EVAL_MS = Number(process.env.STRESS_SLOW_EVAL_MS || 3000);
const WATCHDOG_MS = Number(process.env.STRESS_TIMEOUT_MS || 20 * 60 * 1000);
const OUTDIR = path.join(BUILD, "e2e");
fs.mkdirSync(OUTDIR, { recursive: true });
const log = (...a) => console.log("[stress]", ...a);
const failures = [];
const need = (c, m) => { if (!c) { failures.push(m); console.error("[stress] FAIL:", m); } };

let drv = null, srv = null;
const cleanup = async () => { try { await drv?.close(); } catch {} try { srv?.close(); } catch {} };
const wd = setTimeout(async () => { console.error("[stress] WATCHDOG timeout"); await cleanup(); process.exit(3); }, WATCHDOG_MS);

// ページ内ヘルパ。drv.eval には 1 式として渡す (戻り値は JSON 化可能)
const PAGE = `(() => {
  const h = window.__e2e.host, c = document.getElementById("screen"), v = h.view, mem = window.__e2e.memory;
  const g = (i) => Atomics.load(v.i32, i) >>> 0;
  let tog = 0, bufChanges = 0, lastBuf = mem.buffer;
  const mv = () => { tog ^= 1; c.dispatchEvent(new PointerEvent("pointermove", { clientX: tog ? 100 : 150, clientY: tog ? 170 : 180, buttons: 1, pointerId: 1, bubbles: true })); };
  const frame = () => new Promise((res, rej) => { const t = setTimeout(() => rej(new Error("frame ack timeout 5s")), 5000); h.waitFrameAfter(h.lastFrameSeq).then((s) => { clearTimeout(t); res(s); }); });
  const S0 = (${/* OFF.surf>>2 */ 0x140 >> 2}), SW = 32, GEN = 9, ST = 0;
  window.__s = {
    moves: 0,
    async single(n) { for (let i = 0; i < n; i++) { const p = frame(); mv(); this.moves++; await p; } },
    async toFrames(target) { while (h.frames < target) { const p = frame(); mv(); this.moves++; await p; } },
    async burst(rounds, size) {
      for (let r = 0; r < rounds; r++) {
        const p = frame(); for (let i = 0; i < size; i++) { mv(); this.moves++; } await p;
        while (g(34) !== g(32)) await frame();
      }
    },
    flood(n) { for (let i = 0; i < n; i++) { mv(); this.moves++; } },
    grow(pages) { mem.grow(pages); },
    sample() {
      if (mem.buffer !== lastBuf) { bufChanges++; lastBuf = mem.buffer; }
      const gens = {}; for (let id = 0; id < 16; id++) { const o = S0 + id * SW; if (Atomics.load(v.i32, o + ST) !== 0) gens[id] = v.u32[o + GEN]; }
      return { frames: h.frames, moves: this.moves, inPushed: g(32), inDropped: g(33), inConsumed: g(34), outFullWaits: g(36), presentSeq: g(37), presentDone: g(38), memBytes: mem.buffer.byteLength, bufChanges, gens };
    },
    async idle() { for (let i = 0; i < 200 && (g(34) !== g(32) || g(37) !== g(38)); i++) await new Promise((r) => setTimeout(r, 10)); return g(34) === g(32) && g(37) === g(38); },
    lastEv() { for (let i = h.logs.length - 1; i >= 0; i--) { const m = /^paint ev=(\\d+)/.exec(h.logs[i]); if (m) return +m[1]; } return -1; },
  };
  return true;
})()`;

async function main() {
  const s = await startServer(); srv = s.srv;
  drv = await openDriver(`http://127.0.0.1:${s.port}/`);
  // GUI-23 (#1665): 1 eval の所要時間を採る。SLOW_EVAL_MS 超は [slow-eval] を出す (CLI 既定 action timeout 25 s との切り分け用)
  let evalMax = 0, evalSlow = 0;
  const E = async (e) => {
    const t = Date.now();
    try { return await drv.eval(e); } catch (err) { log(`eval failed after ${Date.now() - t} ms: ${e.slice(0, 40)}`); throw err; }
    finally { const d = Date.now() - t; evalMax = Math.max(evalMax, d); if (d > SLOW_EVAL_MS) { evalSlow++; log(`slow-eval ${d} ms: ${e.slice(0, 40).replace(/\n/g, " ")}`); } }
  };
  log("driver:", drv.name, drv.version, `FRAMES=${FRAMES} SAMPLE=${SAMPLE} FAULT=${FAULT || "-"} GROW=${GROW}`);
  const boot = await E("window.__ready");
  need(boot.sab === true, "wasm memory must be SharedArrayBuffer");
  await E(PAGE);
  const L = (expr) => E(`window.__e2e.host.${expr}`);
  await L(`waitLog("app: created")`); await L(`waitLog("app: timer-done")`);

  // 前段: 実マウスで 2 クリック (cnt=2) → ドラッグ開始 (cnt=3, 始点 30,150)。golden のシナリオと同じ
  const click = async (x, y, ev) => { await drv.mouse("move", x, y); await drv.mouse("down", x, y); await L(`waitLog("paint ev=${ev}")`); await drv.mouse("up", x, y); await L(`waitLog("paint ev=${ev + 1}")`); };
  await click(200, 150, 1); await click(210, 150, 3);
  await drv.mouse("move", 30, 150); await drv.mouse("down", 30, 150); await L(`waitLog("paint ev=5")`);
  await drv.mouse("move", 100, 170);

  const samples = [await E("window.__s.sample()")];
  const first = samples[0];
  const t0 = Date.now(), wall = () => ((Date.now() - t0) / 1000).toFixed(1);
  if (FAULT === "burst") {
    await E("window.__s.flood(200000)");
    await E("window.__s.idle()");
    samples.push(await E("window.__s.sample()"), await E("window.__s.sample()"), await E("window.__s.sample()"));
  } else {
    const nSamples = Math.ceil(FRAMES / SAMPLE);
    for (let i = 1; i <= nSamples; i++) {
      await E(`window.__s.single(${Math.round(SAMPLE * 0.9)})`);
      await E(`window.__s.burst(${Math.max(1, Math.round(SAMPLE * 0.1 / 8))}, 8)`);   // 8 move 連打 (リング上限 1024 の十分内側; guest 側で併合され frame は move 数より少ない)
      await E(`window.__s.toFrames(${first.frames + i * SAMPLE})`);                    // 実フレーム数で SAMPLE 刻みに揃える
      if (GROW && i <= GROW) await E("window.__s.grow(1)");
      if (FAULT === "leak" && i > nSamples / 2) await E("window.__s.grow(1)");
      samples.push(await E("window.__s.sample()"));
      if (i % 5 === 0 || i === nSamples) { const x = samples.at(-1); log(`${wall()}s frames=${x.frames} moves=${x.moves} drop=${x.inDropped} fullWaits=${x.outFullWaits} mem=${x.memBytes} bufChanges=${x.bufChanges}`); }
    }
  }
  const idle = await E("window.__s.idle()");
  need(idle || FAULT === "burst", "guest did not drain input/present rings within 2 s after stress");

  const fails = judgeStress(samples, { minFrames: FAULT === "burst" ? 0 : FRAMES });
  for (const m of fails) { failures.push(m); console.error("[stress] FAIL:", m); }
  const last = samples.at(-1);
  if (GROW) need(last.bufChanges >= 1, `memory.buffer identity never changed (GROW=${GROW} 未発火)`);

  if (!FAULT) {
    // 収束: 実入力で golden の終状態へ (ドラッグ終点 150,180 → up → 'A','b')
    await drv.mouse("move", 150, 180);
    await E("window.__s.idle()");
    let ev = await E("window.__s.lastEv()");
    await drv.mouse("up", 150, 180); await L(`waitLog("paint ev=${ev + 1}")`); ev++;
    for (const ch of ["A", "b"]) { await drv.press(ch); await L(`waitLog("paint ev=${ev + 1}")`); ev++; }
    await E("window.__s.idle()");
    const golden = readPPM(path.join(ROOT, "golden", "final.ppm"));
    const rb = await E(`(async () => { const r = await window.__e2e.host.readback(); let s = ""; const d = r.data; for (let i = 0; i < d.length; i += 0x8000) s += String.fromCharCode.apply(null, d.subarray(i, i + 0x8000)); return { w: r.width, h: r.height, b64: btoa(s) }; })()`);
    const diff = countPixelDiff(Buffer.from(rb.b64, "base64"), golden.data, W, H);
    need(rb.w === W && rb.h === H, `readback size ${rb.w}x${rb.h}`);
    need(diff === 0, `post-stress readback != golden: ${diff} px differ`);
    log(`post-stress readback vs golden: ${diff === 0 ? "EXACT MATCH" : "MISMATCH"} (${diff} differing px of ${W * H})`);
    const st = await L("stats()");
    log("worker stats:", JSON.stringify(st.stats), "frames:", st.frames);
    await drv.press("Escape"); await L(`waitLog("app: destroy")`);
    need((await L("exited")) === 0, "exit code != 0");
    const errs = await E("window.__e2e.errors"); need(errs.length === 0, "page errors: " + JSON.stringify(errs));
    const perr = await drv.pageErrors(); need(perr.length === 0, "driver page errors: " + JSON.stringify(perr));
    fs.writeFileSync(path.join(OUTDIR, "stress.json"), JSON.stringify({ frames: FRAMES, wallSec: +wall(), fault: FAULT, grow: GROW, workerStats: st.stats, samples }, null, 1));
  }
  log(`summary: ${wall()}s frames ${first.frames}→${last.frames} moves=${last.moves} inDropped=${last.inDropped} outFullWaits=${last.outFullWaits} mem ${first.memBytes}→${last.memBytes} bufChanges=${last.bufChanges} gens=${JSON.stringify(last.gens)} (first ${JSON.stringify(first.gens)})`);
  log(`eval: max ${evalMax} ms, slow(>${SLOW_EVAL_MS} ms) ${evalSlow}, load1 ${os.loadavg()[0].toFixed(2)}`);
}

main().then(async () => {
  clearTimeout(wd); await cleanup();
  if (failures.length) { console.error(`[stress] FAILED (${failures.length})${FAULT ? ` [negctl FAULT=${FAULT}: 不合格が正しい挙動]` : ""}`); process.exit(1); }
  console.log("[stress] PASS");
  process.exit(0);
}).catch(async (e) => { clearTimeout(wd); console.error("[stress] ERROR", e); await cleanup(); process.exit(2); });
