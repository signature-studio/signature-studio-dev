// P15 Chrome Worker: 実 OTT (ottl.wasm) を 1 instance (= 1 Memory) だけ instantiate し、その中に
// M 個の OTT 処理オブジェクトを畳み込んで駆動する。plugin 数 M を instance 上限 (124〜125) と切り離す。
// 署名は shared_obj.mjs と同一手順。判定: 全 obj の署名が 6b1696f0 (単独 instance の既知値)。
const OBJ0 = 0x31000000, STRIDE = 0x40000;
const IN0 = 0x34000000, OU0 = 0x34000080, BUF0 = 0x34100000;
const N = 128;
const slot = (i) => ({ obj: OBJ0 + i * STRIDE, inA: IN0 + i * 0x100, ouA: OU0 + i * 0x100, buf: BUF0 + i * 0x2000 });
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const p50 = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };

const wasmP = fetch('/w/ottl.wasm').then((r) => r.arrayBuffer());

async function load() {
  const imports = {
    env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
    wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
  };
  const { instance } = await WebAssembly.instantiate(await wasmP, imports);
  const x = instance.exports;
  x.__wasm_call_ctors();
  x.ott_data_install();
  const run = (va, a, xs = []) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), BigInt(a[2] ?? 0), BigInt(a[3] ?? 0), BigInt(xs[0] ?? 0), BigInt(xs[1] ?? 0), BigInt(xs[2] ?? 0), BigInt(xs[3] ?? 0)));
  return {
    mod: x,
    ctor: (obj) => run(0x18011d400, [obj, 0]),
    setParam: (obj, i, v) => run(0x180120af0, [obj, i], [0, 0, f32b(v)]),
    resume: (obj) => run(0x180120800, [obj]),
    process: (obj, inA, ouA, n) => run(0x18011ec20, [obj, inA, ouA, n]),
  };
}

async function runShared({ m, blk, reps }) {
  const t0 = performance.now();
  const api = await load();
  const tLoad = performance.now() - t0;
  const mem = api.mod.memory.buffer; const U32 = new Uint32Array(mem); const F32 = new Float32Array(mem);
  const t1 = performance.now();
  for (let i = 0; i < m; i++) {
    const s = slot(i);
    api.ctor(s.obj); for (let p = 0; p < 19; p++) api.setParam(s.obj, p, 0.5); api.resume(s.obj);
    for (let k = 0; k < N * 2; k++) F32[s.buf / 4 + k] = Math.fround(Math.sin(k * 0.05) * 0.5);
    U32[s.inA / 4] = s.buf; U32[s.inA / 4 + 2] = s.buf + N * 4; U32[s.ouA / 4] = s.buf + N * 8; U32[s.ouA / 4 + 2] = s.buf + N * 12;
  }
  const tSetup = performance.now() - t1;
  const sigs = [];
  for (let i = 0; i < m; i++) {
    const s = slot(i); let h = 0x811c9dc5 >>> 0;
    for (let k = 1; k <= 1000; k++) { api.process(s.obj, s.inA, s.ouA, N); if (k <= 8 || k === 1000) for (let j = 0; j < 2 * N; j++) h = Math.imul(h ^ U32[s.buf / 4 + 2 * N + j], 16777619) >>> 0; }
    sigs.push(h.toString(16));
  }
  const uniq = [...new Set(sigs)];
  for (let i = 0; i < m; i++) { const s = slot(i); for (let k = 0; k < 300; k++) api.process(s.obj, s.inA, s.ouA, N); }
  const per = [];
  for (let r = 0; r < reps; r++) {
    const t = performance.now();
    for (let b = 0; b < blk; b++) for (let i = 0; i < m; i++) { const s = slot(i); api.process(s.obj, s.inA, s.ouA, N); }
    per.push((performance.now() - t) * 1000 / (blk * m));
  }
  const us = p50(per);
  return {
    runtime_ua: navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] ?? 'unknown',
    m, instances: 1, load_ms: +tLoad.toFixed(2), setup_ms: +tSetup.toFixed(2),
    us_per_block_p50: +us.toFixed(2), us_per_block_min: +Math.min(...per).toFixed(2), us_per_block_max: +Math.max(...per).toFixed(2),
    rtf44_per_obj: +(us / (N / 44.1 * 1000)).toFixed(5),
    sig: uniq, sig_n: sigs.length, sig_ok: uniq.length === 1 && uniq[0] === '6b1696f0',
    memory_mib: +(mem.byteLength / 2 ** 20).toFixed(1),
  };
}

self.onmessage = async (ev) => {
  try { self.postMessage({ ok: true, r: await runShared(ev.data) }); }
  catch (e) { self.postMessage({ ok: false, error: String(e && e.message || e).slice(0, 300) }); }
};
