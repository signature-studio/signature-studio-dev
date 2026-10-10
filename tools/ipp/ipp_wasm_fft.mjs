// wasm 版 FFT を golden (実 IPP の x / fwd(RToPack) / inv(PackToR) 出力) と NRMS 比較。usage: node ipp_wasm_fft.mjs <wasm> <goldenDir> [out.json]
import fs from 'node:fs';
const [, , wasmPath, gdir, outPath] = process.argv;
const X = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(wasmPath)), { env: { emscripten_notify_memory_growth() {} } }).exports;
const cases = JSON.parse(fs.readFileSync(`${gdir}/fft_golden.json`, 'utf8')), blob = fs.readFileSync(`${gdir}/fft_golden.bin`);
const nrms = (a, b) => { let d = 0, r = 0; for (let i = 0; i < a.length; i++) { d += (a[i] - b[i]) ** 2; r += b[i] ** 2; } return Math.sqrt(d / (r + 1e-300)); };
let worst32 = 0, worst64 = 0, bad = 0; const rows = [];
for (const c of cases) {
  const N = 1 << c.order, es = c.dbl ? 8 : 4, T = c.dbl ? Float64Array : Float32Array, sfx = c.dbl ? '64f' : '32f';
  const rd = (k) => new T(blob.buffer.slice(blob.byteOffset + c.off + k * N * es, blob.byteOffset + c.off + (k + 1) * N * es));
  const x = rd(0), fwdRef = rd(1), invRef = rd(2);
  const sz = X.malloc(16), pa = sz, pb = sz + 4, pc = sz + 8;
  X[`ippsFFTGetSize_R_${sfx}`](c.order, c.flag, 0, pa, pb, pc);
  const dv = new DataView(X.memory.buffer); const specSize = dv.getInt32(pa, true);
  const spec = X.malloc(specSize + 64), pspec = X.malloc(8); let st = X[`ippsFFTInit_R_${sfx}`](pspec, c.order, c.flag, 0, spec, 0);
  const sp = new DataView(X.memory.buffer).getUint32(pspec, true);
  const pin = X.malloc(N * es + 64), pout = X.malloc(N * es + 64);
  new T(X.memory.buffer, pin, N).set(x);
  st |= X[`ippsFFTFwd_RToPack_${sfx}`](pin, pout, sp, 0);
  const fwd = new T(X.memory.buffer.slice(pout, pout + N * es)); const e1 = nrms(fwd, fwdRef);
  new T(X.memory.buffer, pin, N).set(fwdRef);
  st |= X[`ippsFFTInv_PackToR_${sfx}`](pin, pout, sp, 0);
  const inv = new T(X.memory.buffer.slice(pout, pout + N * es)); const e2 = nrms(inv, invRef);
  const e = Math.max(e1, e2); if (c.dbl) worst64 = Math.max(worst64, e); else worst32 = Math.max(worst32, e);
  const lim = c.dbl ? 1e-12 : 5e-6; if (e > lim || st) bad++;
  rows.push({ ...c, nrms_fwd: e1, nrms_inv: e2, st });
}
console.log(`fft wasm vs real IPP: cases=${cases.length} worstNRMS32f=${worst32.toExponential(2)} worstNRMS64f=${worst64.toExponential(2)} bad=${bad}`);
if (outPath) fs.writeFileSync(outPath, JSON.stringify({ worst32, worst64, bad, rows }, null, 1));
process.exit(bad ? 1 : 0);
