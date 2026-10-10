// FFT 性能ベンチ: 差替え前 (旧: 倍精度基数2, git HEAD の src/ipp_fft.c) vs 差替え後 (新: pffft)。
// 同一条件 = 同一 node / 同一入力列 / 同一 iteration 数 / 同一 emcc フラグの 2 本の wasm を
//   関数直接呼出 (shim 経由ではない; tools/ipp/ipp_wasm_bench.mjs と同一方法) で測る。
// pBuffer は NULL (0) で統一 (旧実装は内部 malloc、新実装は内部 scratch 確保)。加えて新実装は
//   IPP 流の buffer あり (GetSize の pBufSize を渡す) も測る。
// usage: node bench_fft.mjs <fft_old.wasm> <fft_new.wasm> [out.json]
import fs from 'node:fs';
const [, , oldPath, newPath, outPath] = process.argv;
const load = (p) => new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(p)), { env: { emscripten_notify_memory_growth() {} } }).exports;

const row = (label, ns, iters) => `${label.padEnd(30)} ${(ns).toFixed(0).padStart(7)} ns/call  (iters=${iters})`;
const bench = (X, fn, iters) => {
  for (let i = 0; i < 100; i++) fn();
  const runs = [];
  for (let r = 0; r < 3; r++) {
    const t = process.hrtime.bigint();
    for (let i = 0; i < iters; i++) fn();
    runs.push(Number(process.hrtime.bigint() - t) / iters);
  }
  return Math.min(...runs);
};

const res = {};
for (const [tag, path] of [['old', oldPath], ['new', newPath]]) {
  const X = load(path);
  const dv = new DataView(X.memory.buffer);
  const out = res[tag] = {};
  for (const dbl of [0, 1]) {
    const sfx = dbl ? '64f' : '32f', ES = dbl ? 8 : 4;
    const T = dbl ? Float64Array : Float32Array;
    const gs = X[`ippsFFTGetSize_R_${sfx}`], init = X[`ippsFFTInit_R_${sfx}`];
    for (const order of [8, 10, 12, 14, 16]) {
      const N = 1 << order;
      const sz3 = X.malloc(16); gs(order, 8, 0, sz3, sz3 + 4, sz3 + 8);
      const specSize = dv.getInt32(sz3, true), workSize = dv.getInt32(sz3 + 8, true);
      const spec = X.malloc(specSize + 64), pspec = X.malloc(8);
      init(pspec, order, 8, 0, spec, 0);
      const sp = dv.getUint32(pspec, true);
      const pin = X.malloc(N * ES + 64), pout = X.malloc((N + 2) * ES + 64), pbuf = X.malloc(workSize + 64);
      const f = new T(X.memory.buffer, pin, N); for (let i = 0; i < N; i++) f[i] = Math.sin(i * 0.01);
      const iters = Math.max(200, Math.round(3e7 / N / (dbl ? 2 : 1)));
      const name = `${sfx}_N${N}`;
      out[name] = {};
      out[name].Fwd_RToPack = bench(X, () => X[`ippsFFTFwd_RToPack_${sfx}`](pin, pout, sp, 0), iters);
      out[name].Inv_PackToR = bench(X, () => X[`ippsFFTInv_PackToR_${sfx}`](pout, pin, sp, 0), iters);
      out[name].Fwd_RToPack_I = bench(X, () => X[`ippsFFTFwd_RToPack_${sfx}_I`](pin, sp, 0), iters);
      if (tag === 'new') {
        out[name].Fwd_RToPack_buf = bench(X, () => X[`ippsFFTFwd_RToPack_${sfx}`](pin, pout, sp, pbuf), iters);
        out[name].Fwd_RToCCS = bench(X, () => X[`ippsFFTFwd_RToCCS_${sfx}`](pin, pout, sp, 0), iters);
        out[name].Fwd_RToPerm = bench(X, () => X[`ippsFFTFwd_RToPerm_${sfx}`](pin, pout, sp, 0), iters);
        out[name].Inv_PermToR = bench(X, () => X[`ippsFFTInv_PermToR_${sfx}`](pout, pin, sp, 0), iters);
      }
      X.free(pbuf);
    }
  }
}
const lines = [];
for (const k of Object.keys(res.new)) {
  const o = res.old[k]?.Fwd_RToPack, n = res.new[k].Fwd_RToPack, nb = res.new[k].Fwd_RToPack_buf;
  lines.push(`${k}: old ${o.toFixed(0)} ns -> new ${n.toFixed(0)} ns (buf=${nb.toFixed(0)})  speedup ${(o / n).toFixed(1)}x / ${(o / nb).toFixed(1)}x`);
}
console.log(lines.join('\n'));
if (outPath) fs.writeFileSync(outPath, JSON.stringify(res, null, 1));
