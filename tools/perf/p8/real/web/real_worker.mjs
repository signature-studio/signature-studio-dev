// Chrome Dedicated Worker 側: 実 OTT (ottl.wasm) を N 個 instance 化し、bench_real.mjs と同一手順で駆動する。
// glue を使わず import (env/wasi の 5 関数) を直接満たす。初期化は glue の順 (__wasm_call_ctors → ott_data_install)。
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const N = 128;
const p50 = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };

let wasmBytes = null;
async function load() {
  if (!wasmBytes) wasmBytes = new Uint8Array(await (await fetch('/w/ottl.wasm')).arrayBuffer());
  const imports = {
    env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
    wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
  };
  const { instance } = await WebAssembly.instantiate(wasmBytes, imports);
  const x = instance.exports;
  x.__wasm_call_ctors();
  x.ott_data_install();
  const big = (v) => BigInt(v);
  const run = (va, a, xs = []) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), big(a[0] ?? 0), big(a[1] ?? 0), big(a[2] ?? 0), big(a[3] ?? 0), big(xs[0] ?? 0), big(xs[1] ?? 0), big(xs[2] ?? 0), big(xs[3] ?? 0)));
  return {
    mod: x,
    ctor: (obj) => run(0x18011d400, [obj, 0]),
    setParam: (obj, i, v) => run(0x180120af0, [obj, i], [0, 0, f32b(v)]),
    resume: (obj) => run(0x180120800, [obj]),
    process: (obj, inA, ouA, n) => run(0x18011ec20, [obj, inA, ouA, n]),
  };
}

async function runReal({ n, blk, reps }) {
  const t0 = performance.now();
  const apis = [];
  for (let i = 0; i < n; i++) apis.push(await load());
  const tLoad = performance.now() - t0;

  const t1 = performance.now();
  for (const api of apis) {
    const mem = api.mod.memory.buffer; const U32 = new Uint32Array(mem); const F32 = new Float32Array(mem);
    api.ctor(OBJ); for (let i = 0; i < 19; i++) api.setParam(OBJ, i, 0.5); api.resume(OBJ);
    for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
    U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
  }
  const tSetup = performance.now() - t1;

  const sigs = [];
  for (const api of apis) {
    const U32 = new Uint32Array(api.mod.memory.buffer); let h = 0x811c9dc5 >>> 0;
    for (let k = 1; k <= 1000; k++) { api.process(OBJ, IN_A, OU_A, N); if (k <= 8 || k === 1000) for (let i = 0; i < 2 * N; i++) h = Math.imul(h ^ U32[BUF / 4 + 2 * N + i], 16777619) >>> 0; }
    sigs.push(h.toString(16));
  }

  for (const api of apis) for (let k = 0; k < 300; k++) api.process(OBJ, IN_A, OU_A, N);
  const per = [];
  for (let r = 0; r < reps; r++) {
    const t = performance.now();
    for (let b = 0; b < blk; b++) for (const api of apis) api.process(OBJ, IN_A, OU_A, N);
    per.push((performance.now() - t) * 1000 / (blk * n));
  }
  const us = p50(per);
  return {
    runtime_ua: navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] ?? 'unknown',
    load_ms: +tLoad.toFixed(2), setup_ms: +tSetup.toFixed(2),
    us_per_block_p50: +us.toFixed(2), us_per_block_min: +Math.min(...per).toFixed(2), us_per_block_max: +Math.max(...per).toFixed(2),
    rtf44_per_instance: +(us / (N / 44.1 * 1000)).toFixed(5),
    sig: [...new Set(sigs)], sig_n: sigs.length,
  };
}

// Memory 本数上限: 1 Worker 内で instance を max 本まで生成し、失敗した本数 (= 成功数) を返す。
async function probeLimit({ max }) {
  const keep = []; let err = null;
  for (let i = 0; i < max; i++) {
    try { keep.push(await load()); } catch (e) { err = String(e && e.message || e).slice(0, 200); break; }
  }
  return { limit_probe_max: max, instances_ok: keep.length, error: err };
}

self.onmessage = async (ev) => {
  try { self.postMessage({ ok: true, r: ev.data.limit ? await probeLimit(ev.data) : await runReal(ev.data) }); }
  catch (e) { self.postMessage({ ok: false, error: String(e && e.stack || e) }); }
};
