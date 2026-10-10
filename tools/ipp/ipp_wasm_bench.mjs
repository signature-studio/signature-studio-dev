// wasm 版 ipp_min のスループット (n=4096 float, ns/call)。usage: node ipp_wasm_bench.mjs a.wasm [b.wasm ...]
import fs from 'node:fs';
const n = 4096, iters = 100000;
const out = {};
for (const p of process.argv.slice(2)) {
  const X = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(p)), { env: { emscripten_notify_memory_growth() {} } }).exports;
  const a = X.malloc(n * 4 + 64), d = X.malloc(n * 4 + 64);
  const F = new Float32Array(X.memory.buffer); for (let i = 0; i < n; i++) { F[a / 4 + i] = (i % 97) * 0.01 + 0.5; F[d / 4 + i] = 0.25; }
  const ops = { Add_32f_I: () => X.ippsAdd_32f_I(a, d, n), MulC_32f_I: () => X.ippsMulC_32f_I(1.0000001, d, n), Move_8u_16KB: () => X.ippsMove_8u(a, d, n * 4),
    Sqrt_32f_A11: () => X.ippsSqrt_32f_A11(a, d, n), Exp_32f_A11: () => X.ippsExp_32f_A11(a, d, n) };
  const sz = X.malloc(16); X.ippsFFTGetSize_R_32f(12, 1, 0, sz, sz + 4, sz + 8); const specSize = new DataView(X.memory.buffer).getInt32(sz, true);
  const spec = X.malloc(specSize + 64), pps = X.malloc(8); X.ippsFFTInit_R_32f(pps, 12, 1, 0, spec, 0); const sp = new DataView(X.memory.buffer).getUint32(pps, true);
  const fin = X.malloc(4096 * 4 + 64), fout = X.malloc(4096 * 4 + 64); for (let i = 0; i < 4096; i++) F[fin / 4 + i] = Math.sin(i * 0.01);
  ops.FFTFwd_RToPack_32f_4096 = () => X.ippsFFTFwd_RToPack_32f(fin, fout, sp, 0);
  out[p.split('/').pop()] = {};
  for (const [k, f] of Object.entries(ops)) { const it = k.startsWith('FFT') ? 5000 : iters; for (let i = 0; i < 200; i++) f(); const t = process.hrtime.bigint(); for (let i = 0; i < it; i++) f(); out[p.split('/').pop()][k] = Math.round(Number(process.hrtime.bigint() - t) / it); }
}
console.log(JSON.stringify(out));
