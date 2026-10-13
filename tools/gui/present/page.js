// page.js — GUI-4 present e2e のページ側 (CDP から window.__present.* を呼ぶ)。
//   golden : 同一の模擬 guest 操作列を 4 方式の GuiRenderer へ流し、毎ステップ 画面(読戻し) == 独立 oracle を画素単位で比較
//   tearing: 全面 1 色フレームを書き続ける guest worker と rAF 同期の描画器で、tear した flush 数を数える (seqlock off / on)
//   bench  : 同一シーンの flush 時間 (CPU putImageData 経路 vs WebGL2 経路)
import { MockGuest, memPagesFor } from "/present/mock_guest.js";
import { W as WORD } from "/js/gui_proto.js";

const container = document.getElementById("c");
let reqId = 0;

function boot() {
  return { crossOriginIsolated: self.crossOriginIsolated === true, rafType: typeof requestAnimationFrame, ua: navigator.userAgent };
}

async function makeRenderer(name, present, width, height, surfBytes, pos, test = null) {
  const memory = new WebAssembly.Memory({ initial: memPagesFor(surfBytes), maximum: memPagesFor(surfBytes), shared: true });
  const canvas = document.createElement("canvas");
  canvas.width = width; canvas.height = height;
  if (pos) { canvas.style.left = pos[0] + "px"; canvas.style.top = pos[1] + "px"; container.append(canvas); }
  const off = canvas.transferControlToOffscreen();
  const worker = new Worker("/present/worker.js", { type: "module" });
  const guest = new MockGuest(memory, 0, width, height);
  const waiters = new Map();
  const frameWaiters = [];
  let ready;
  const readyP = new Promise((res, rej) => { ready = { res, rej }; });
  worker.onmessage = (e) => {
    const m = e.data;
    if (m.type === "ready") ready.res(m.info);
    else if (m.type === "error") ready.rej(new Error(m.message));
    else if (m.id && waiters.has(m.id)) { const w = waiters.get(m.id); waiters.delete(m.id); w(m); }
  };
  worker.onerror = (e) => ready.rej(new Error("worker error: " + e.message));
  worker.postMessage({ type: "init", canvas: off, memory, base: 0, width, height, present, test }, [off]);
  const info = await readyP;
  const ask = (type, extra = {}) => new Promise((res) => { const id = ++reqId; waiters.set(id, res); worker.postMessage({ type, id, ...extra }); });
  void frameWaiters;
  return {
    name, present, info, guest, worker, memory,
    readback: async () => new Uint8Array((await ask("readback")).data),
    stats: () => ask("stats"),
    mode: (mode) => ask("mode", { mode }),
    inject: (surf) => ask("inject", { surf }),
    reset: () => ask("reset"),
    async waitAck(seq, timeoutMs = 8000) {
      const t0 = performance.now();
      for (;;) {
        const cur = Atomics.load(guest.i32, WORD.presentDoneSeq) >>> 0;
        if (cur >= seq) return performance.now() - t0;
        const left = timeoutMs - (performance.now() - t0);
        if (left <= 0) throw new Error(`${name}: ack timeout seq=${seq} done=${cur}`);
        const r = Atomics.waitAsync(guest.i32, WORD.presentDoneSeq, cur, left);
        if (r.async) await r.value;
      }
    },
  };
}

// ---------------- golden ----------------
function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

/** 決定的な操作列 (全方式に同一に適用) */
function buildScenario(W, H, steps) {
  const R = rng(180);
  const ri = (a, b) => a + Math.floor(R() * (b - a));
  const surf = {}; // 幾何の追跡 (生成側)
  const sc = [];
  const mk = (id, x, y, w, h, z, visible = 1) => { surf[id] = { x, y, w, h, z, visible }; return { op: "create", id, x, y, w, h, z, visible }; };
  sc.push({ ops: [mk(0, 0, 0, W, H, 1), mk(1, 100, 50, 300, 200, 2), mk(2, -40, 200, 200, 300, 3), mk(3, 500, 300, 120, 100, 4, 0)].concat(
    [0, 1, 2, 3].map((id) => ({ op: "paint", id, l: 0, t: 0, r: surf[id].w, b: surf[id].h, seed: 1000 + id })), [0, 1, 2, 3].map((id) => ({ op: "present", id, l: 0, t: 0, r: surf[id].w, b: surf[id].h }))), label: "init" });
  let seed = 5000, topZ = 4;
  for (let s = 1; s <= steps; s++) {
    const ops = []; let label = "dirty";
    const kind = s % 9;
    if (kind === 3) { const id = 1 + (s % 3); topZ++; surf[id].z = topZ; ops.push({ op: "change", id, patch: { z: topZ } }); label = `z-front s${id}`; }
    else if (kind === 4) {
      // 前面 2 枚 (id 大 = s3 が z 小、id 小 = s2 が z 大) を全面 s0 の dirty 矩形に重ねる (id 順だと z 逆転描画になる)
      topZ += 2; surf[3].visible = 1; surf[3].x = 60; surf[3].y = 260; surf[3].z = topZ - 1; surf[2].z = topZ; surf[2].visible = 1;
      ops.push({ op: "change", id: 3, patch: { visible: 1, x: 60, y: 260, z: topZ - 1 } }, { op: "change", id: 2, patch: { visible: 1, z: topZ } });
      ops.push({ op: "paint", id: 0, l: 0, t: 0, r: W, b: H, seed: seed++ }, { op: "present", id: 0, l: 0, t: 0, r: W, b: H });
      label = "front-overlap s2>s3 over s0";
    }
    else if (kind === 5) { const id = 3; surf[id].visible = surf[id].visible ? 0 : 1; ops.push({ op: "change", id, patch: { visible: surf[id].visible } }); label = `visible s3=${surf[id].visible}`; }
    else if (kind === 6) { const id = 1; surf[id].x = ri(-30, 300); surf[id].y = ri(-20, 200); ops.push({ op: "change", id, patch: { x: surf[id].x, y: surf[id].y } }); label = "move s1"; }
    else if (kind === 7) {
      const id = 1, w = ri(120, 420), h = ri(80, 300); surf[id].w = w; surf[id].h = h;
      ops.push({ op: "change", id, patch: { w, h } }, { op: "paint", id, l: 0, t: 0, r: w, b: h, seed: seed++ }, { op: "present", id, l: 0, t: 0, r: w, b: h }); label = `resize s1 ${w}x${h}`;
    } else if (kind === 8) {
      ops.push({ op: "destroy", id: 2 }); const w = ri(100, 260), h = ri(100, 260), x = ri(0, W - 50), y = ri(0, H - 50);
      topZ++; ops.push(mk(2, x, y, w, h, topZ), { op: "paint", id: 2, l: 0, t: 0, r: w, b: h, seed: seed++ }, { op: "present", id: 2, l: 0, t: 0, r: w, b: h }); label = `recreate s2 ${w}x${h}@${x},${y}`;
    }
    // どのステップも 1〜4 個の dirty 矩形 (隣接/重複/離散を混ぜる)
    const k = ri(1, 5);
    for (let j = 0; j < k; j++) {
      const id = ri(0, 4); const g = surf[id]; if (!g) continue;
      let w = ri(1, Math.max(2, Math.min(g.w, 120))), h = ri(1, Math.max(2, Math.min(g.h, 90)));
      let l = ri(0, Math.max(1, g.w - w + 1)), t = ri(0, Math.max(1, g.h - h + 1));
      if (j > 0 && R() < 0.5 && ops.length) { const prev = ops.filter((o) => o.op === "present" && o.id === id).pop(); if (prev) { l = Math.min(g.w - 1, prev.r); t = prev.t; w = Math.min(w, g.w - l); h = Math.min(h, g.h - t); } } // 辺で接する矩形
      ops.push({ op: "paint", id, l, t, r: l + w, b: t + h, seed: seed++ }, { op: "present", id, l, t, r: l + w, b: t + h });
    }
    sc.push({ ops, label: `${label} (+${k} rects)` });
  }
  return sc;
}

function applyOps(g, ops) {
  for (const o of ops) {
    if (o.op === "create") g.create(o.id, o.x, o.y, o.w, o.h, o.z, o.visible);
    else if (o.op === "paint") g.paint(o.id, o.l, o.t, o.r, o.b, o.seed);
    else if (o.op === "present") g.present(o.id, o.l, o.t, o.r, o.b);
    else if (o.op === "change") g.change(o.id, o.patch);
    else if (o.op === "destroy") g.destroy(o.id);
  }
}

function diffCount(a, b) {
  const ua = new Uint32Array(a.buffer, a.byteOffset, a.byteLength >> 2), ub = new Uint32Array(b.buffer, b.byteOffset, b.byteLength >> 2);
  let n = 0, first = -1;
  for (let i = 0; i < ua.length; i++) if (ua[i] !== ub[i]) { if (first < 0) first = i; n++; }
  return { n, first };
}
const b64 = (u8) => { let s = ""; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };

const CONFIGS = [
  { name: "cpu-immediate (従来経路)", present: {} },
  { name: "gl-direct-immediate", present: { backend: "webgl2", upload: "direct" } },
  { name: "gl-staged-raf-seqlock", present: { backend: "webgl2", sync: "raf", seqlock: true, upload: "staged" } },
  { name: "cpu-raf-seqlock", present: { backend: "2d", sync: "raf", seqlock: true } },
];

async function runGolden(steps = 45) {
  const W = 640, H = 360;
  const rs = [];
  for (let i = 0; i < CONFIGS.length; i++) rs.push(await makeRenderer(CONFIGS[i].name, CONFIGS[i].present, W, H, 6 * 1024 * 1024, [(i % 2) * W, Math.floor(i / 2) * H]));
  const scenario = buildScenario(W, H, steps);
  const per = rs.map(() => ({ diffPx: 0, steps: 0, failedSteps: [], first: null }));
  let compared = 0;
  for (let si = 0; si < scenario.length; si++) {
    const seqs = rs.map((r) => { applyOps(r.guest, scenario[si].ops); return r.guest.frameEnd(); });
    await Promise.all(rs.map((r, i) => r.waitAck(seqs[i])));
    const oracle = rs[0].guest.oracle();
    for (let i = 0; i < rs.length; i++) {
      const o = i === 0 ? oracle : rs[i].guest.oracle();
      if (diffCount(oracle, o).n !== 0) throw new Error("oracle differs between guests (scenario not deterministic)");
      const rb = await rs[i].readback();
      const d = diffCount(oracle, rb);
      per[i].steps++; per[i].diffPx += d.n;
      if (d.n) { per[i].failedSteps.push(`${si}:${scenario[si].label}:${d.n}`); if (!per[i].first) per[i].first = { step: si, label: scenario[si].label, index: d.first, want: [...oracle.subarray(d.first * 4, d.first * 4 + 4)], got: [...rb.subarray(d.first * 4, d.first * 4 + 4)] }; }
    }
    compared += W * H;
  }
  // ネガティブコントロール: gl 方式の guest 画素を present せずに 1 px 書き換え -> oracle との差が丁度 1 px で検出されること
  const neg = {};
  {
    const r = rs[1]; let x = 5, y = 5;
    const s = r.guest.topSurfaceAt(x, y); const px = r.guest.px(s.id);
    const idx = (y - s.y) * (s.stride >> 2) + (x - s.x); const save = px[idx];
    px[idx] = save ^ 0x00ffffff;
    const o2 = r.guest.oracle(); const rb = await r.readback();
    neg.modifiedPixelDiff = diffCount(o2, rb).n;
    px[idx] = save;
  }
  const finals = [];
  for (let i = 0; i < rs.length; i++) finals.push(rs[i].guest.oracle());
  const stats = [];
  for (const r of rs) { const st = await r.stats(); stats.push({ name: r.name, info: r.info, stats: st.stats, gl: st.gl, frames: st.frames }); }
  return { W, H, steps: scenario.length, comparedPixelsPerRenderer: compared, results: CONFIGS.map((c, i) => ({ name: c.name, info: rs[i].info, ...per[i] })), negative: neg, stats, oracleB64: b64(finals[0]), layout: rs.map((r, i) => ({ name: r.name, left: (i % 2) * W, top: Math.floor(i / 2) * H })) };
}

// ---------------- tearing ----------------
async function runTearing({ frames = 90, periodMs = 16, rowWorkUs = 8, width = 1280, height = 720 } = {}) {
  const out = [];
  const variants = [
    { name: "gl raf seqlock=off", present: { backend: "webgl2", sync: "raf", seqlock: false } },
    { name: "gl raf seqlock=on", present: { backend: "webgl2", sync: "raf", seqlock: true } },
    { name: "cpu raf seqlock=off", present: { backend: "2d", sync: "raf", seqlock: false } },
    { name: "cpu raf seqlock=on", present: { backend: "2d", sync: "raf", seqlock: true } },
  ];
  for (const v of variants) {
    container.replaceChildren();
    const r = await makeRenderer(v.name, v.present, width, height, width * height * 4 + (1 << 20), null);
    await r.mode({ checkUniform: true });
    const gw = new Worker("/present/guest_worker.js", { type: "module" });
    const done = new Promise((res, rej) => { gw.onmessage = (e) => res(e.data); gw.onerror = (e) => rej(new Error("guest worker: " + e.message)); });
    gw.postMessage({ memory: r.memory, base: 0, width, height, frames, periodMs, rowWorkUs });
    const d = await done;
    await r.waitAck(d.seq, 15000);
    // 持ち越し (seqlock) の flush が落ち着くまで: 最終フレームの色が画面に出ること
    let final = null, settled = false;
    for (let k = 0; k < 60 && !settled; k++) {
      const rb = new Uint32Array((await r.readback()).buffer);
      let uni = true; for (let i = 1; i < rb.length; i++) if (rb[i] !== rb[0]) { uni = false; break; }
      const expect = ((d.lastColor & 0xff00ff00) | ((d.lastColor & 0xff) << 16) | ((d.lastColor >>> 16) & 0xff)) >>> 0; // BGRA -> RGBA(LE u32), alpha 255
      final = { uniform: uni, pixel0: rb[0] >>> 0, expect: (expect | 0xff000000) >>> 0 };
      settled = uni && final.pixel0 === final.expect;
      if (!settled) await new Promise((res) => setTimeout(res, 20));
    }
    const st = await r.stats();
    out.push({ name: v.name, guest: d, finalFrameShown: settled, final, stats: st.stats, acc: st.acc, info: st.info, frames: st.frames });
    gw.terminate(); r.worker.terminate();
  }
  return { frames, periodMs, rowWorkUs, width, height, variants: out };
}

// ---------------- seqlock (決定的) ----------------
// guest が書込み中 (wseq 奇数) の surface は読まない: 画面は直前の整合フレームのまま / wseq が偶数に戻ったら新フレームが出る。seqlock off では即座に出る (対照)。
async function runSeqlockDet() {
  const W = 320, H = 200, out = [];
  const eq = (a, b) => diffCount(a, b).n === 0;
  for (const v of [
    { name: "gl immediate", present: { backend: "webgl2", seqlock: true } },
    { name: "gl raf", present: { backend: "webgl2", sync: "raf", seqlock: true } },
    { name: "cpu immediate", present: { backend: "2d", seqlock: true } },
    { name: "cpu raf", present: { backend: "2d", sync: "raf", seqlock: true } },
    { name: "gl immediate (seqlock off)", present: { backend: "webgl2", seqlock: false } },
  ]) {
    container.replaceChildren();
    const r = await makeRenderer(v.name, v.present, W, H, W * H * 4 + (1 << 20), null);
    const g = r.guest, on = v.present.seqlock === true;
    g.create(0, 0, 0, W, H, 1); g.paint(0, 0, 0, W, H, 11); g.present(0, 0, 0, W, H); await r.waitAck(g.frameEnd());
    const frameA = g.oracle();
    const okA = eq(frameA, await r.readback());
    g.wseqBegin(0);                                  // guest が次フレームを描画中
    g.paint(0, 20, 20, 120, 100, 22); g.present(0, 20, 20, 120, 100); await r.waitAck(g.frameEnd());
    const frameB = g.oracle();
    const during = await r.readback();
    const showsOld = eq(frameA, during), showsNew = eq(frameB, during);
    const s1 = (await r.stats()).stats;
    g.wseqEnd(0);                                    // 静止 -> 持ち越した矩形が再試行されて表示される
    let converged = false; const t0 = performance.now();
    while (performance.now() - t0 < 3000) { if (eq(frameB, await r.readback())) { converged = true; break; } await new Promise((res) => setTimeout(res, 10)); }
    const s2 = (await r.stats()).stats;
    out.push({ name: v.name, seqlock: on, initialOk: okA, duringShowsOld: showsOld, duringShowsNew: showsNew, deferred: s1.seqDeferred, converged, convergeMs: Math.round(performance.now() - t0), forced: s2.seqForced });
    r.worker.terminate();
  }
  return out;
}

// ---------------- seqlock (決定的; 検証中の書込み開始) ----------------
// runSeqlockDet は「検証の前から wseq が奇数」の経路しか通らない。ここでは surface を読んだ直後 (検証の前) に guest が書込みを始める経路を模擬する:
// 読んだ内容は捨てて画面は直前の整合フレームのまま / wseq が偶数に戻ったら新フレームが出る。(旧実装の WebGL2 は検証前に texSubImage2D してこの時点で新フレームを表示した)
async function runSeqlockMid() {
  const W = 320, H = 200, out = [];
  const eq = (a, b) => diffCount(a, b).n === 0;
  for (const v of [
    { name: "gl immediate", present: { backend: "webgl2", seqlock: true } },
    { name: "gl raf", present: { backend: "webgl2", sync: "raf", seqlock: true } },
    { name: "cpu immediate", present: { backend: "2d", seqlock: true } },
    { name: "cpu raf", present: { backend: "2d", sync: "raf", seqlock: true } },
  ]) {
    container.replaceChildren();
    const r = await makeRenderer(v.name, v.present, W, H, W * H * 4 + (1 << 20), null, { injectWrite: true });
    const g = r.guest;
    g.create(0, 0, 0, W, H, 1); g.paint(0, 0, 0, W, H, 11); g.present(0, 0, 0, W, H); await r.waitAck(g.frameEnd());
    const frameA = g.oracle();
    const okA = eq(frameA, await r.readback());
    g.paint(0, 20, 20, 120, 100, 22); g.present(0, 20, 20, 120, 100);   // 書込みは完了済み。worker が読んだ直後に次の書込みが始まる
    await r.inject(0);
    await r.waitAck(g.frameEnd());
    const frameB = g.oracle();
    const during = await r.readback();
    const s1 = await r.stats();
    g.wseqEnd(0);                                    // 静止 -> 持ち越した矩形が再試行されて表示される
    let converged = false; const t0 = performance.now();
    while (performance.now() - t0 < 3000) { if (eq(frameB, await r.readback())) { converged = true; break; } await new Promise((res) => setTimeout(res, 10)); }
    const s2 = await r.stats();
    out.push({ name: v.name, initialOk: okA, injected: s1.injected, duringShowsOld: eq(frameA, during), duringShowsNew: eq(frameB, during), retries: s1.stats.seqRetries, deferred: s1.stats.seqDeferred, converged, convergeMs: Math.round(performance.now() - t0), forced: s2.stats.seqForced });
    r.worker.terminate();
  }
  return out;
}

// ---------------- backend "auto" の降格 ----------------
// auto は WebGL2 のシェーダがコンパイルできない環境で 2D へ降格する (none = 正常 → webgl2 / all = 降格 → 2d / afterProbe = プローブは通り描画先だけ失敗 → 降格不能なので明示エラー)
async function runAutoFallback() {
  const out = [];
  for (const kind of ["none", "all", "afterProbe"]) {
    container.replaceChildren();
    try {
      const r = await makeRenderer(`auto/${kind}`, { backend: "auto" }, 64, 48, 1 << 20, null, kind === "none" ? null : { breakShader: kind });
      const rb = await r.readback();
      out.push({ kind, backend: r.info.backend, error: null, readbackBytes: rb.length });
      r.worker.terminate();
    } catch (e) {
      out.push({ kind, backend: null, error: String(e && e.message || e).split("\n")[0] });
    }
  }
  return out;
}

// ---------------- bench ----------------
async function runBench({ sizes = [[1280, 720], [1920, 1080]], frames = 60, warm = 8, reps = 3 } = {}) {
  const out = [];
  const scenarios = (W, H) => [
    { name: "full 100%", rects: [[0, 0, W, H]] },
    { name: "half 25%", rects: [[0, 0, W >> 1, H >> 1]] },
    { name: "small 64x64", rects: [[100, 100, 164, 164]] },
    { name: "multi 8x(128x72)", rects: Array.from({ length: 8 }, (_, i) => [(i % 4) * (W >> 2) + 8, (i >> 2) * (H >> 1) + 8, (i % 4) * (W >> 2) + 8 + 128, (i >> 2) * (H >> 1) + 8 + 72]) },
  ];
  const cfgs = [
    { name: "cpu putImageData", present: { backend: "2d" } },
    { name: "gl direct", present: { backend: "webgl2", upload: "direct" } },
    { name: "gl staged", present: { backend: "webgl2", upload: "staged" } },
  ];
  for (const [W, H] of sizes) {
    for (const c of cfgs) {
      container.replaceChildren();
      const r = await makeRenderer(c.name, c.present, W, H, W * H * 4 + (1 << 20), null);
      r.guest.create(0, 0, 0, W, H, 1);
      r.guest.paint(0, 0, 0, W, H, 77);
      r.guest.present(0, 0, 0, W, H);
      await r.waitAck(r.guest.frameEnd());
      for (const sc of scenarios(W, H)) {
        const runs = [];
        for (let rep = 0; rep < reps; rep++) {
          await r.mode({ syncGpu: false, checkUniform: false });
          const doFrames = async (n) => {
            const t0 = performance.now();
            for (let f = 0; f < n; f++) {
              for (const q of sc.rects) r.guest.present(0, q[0], q[1], q[2], q[3]);
              await r.waitAck(r.guest.frameEnd());
            }
            return (performance.now() - t0) / n;
          };
          await doFrames(warm);
          await r.reset(); await r.mode({ syncGpu: false });
          const wall = await doFrames(frames);
          const s1 = await r.stats();
          await r.reset(); await r.mode({ syncGpu: true });
          await doFrames(frames);
          const s2 = await r.stats();
          runs.push({ submitMs: s1.stats.flushMs / s1.stats.flushes, wallMs: wall, syncedFlushMs: s2.stats.flushMs / s2.stats.flushes, gpuSyncMs: s2.acc.syncN ? s2.acc.syncMs / s2.acc.syncN : 0, rectsPerFrame: s1.stats.rects / s1.stats.flushes, mpixPerFrame: s1.stats.rectPixels / s1.stats.flushes / 1e6 });
        }
        out.push({ size: `${W}x${H}`, config: c.name, backend: r.info.backend, upload: r.info.upload, scenario: sc.name, runs });
      }
      r.worker.terminate();
    }
  }
  return { frames, warm, reps, results: out };
}

window.__present = { boot, runGolden, runTearing, runSeqlockDet, runSeqlockMid, runAutoFallback, runBench };
window.__ready = boot();
