// PERF-P28 (#5403): instr_fill.py で計装した wasm を使い、vtable (0x30203BD0) に重なる memory.fill を記録する。
// 146 回目の ctor まで同じ手順で回し、LOG (0x35F84000) を出す。
//   node tools/perf/p15/ctor_fill_watch.mjs <instrumented.wasm>
import fs from 'node:fs';

const wasmPath = process.argv[2];
const OBJ0 = 0x31000000, STRIDE = 0x40000, IN0 = 0x34000000, OU0 = 0x34000080, BUF0 = 0x34100000, N = 128;
const BUD = 0x35F80000, LOG = 0x35F84000, VT = 0x30203BD0;
const slot = (i) => ({ obj: OBJ0 + i * STRIDE, inA: IN0 + i * 0x100, ouA: OU0 + i * 0x100, buf: BUF0 + i * 0x2000 });
const fdWrite = (fd, iovs, n, nw) => {
  const m = new Uint32Array(x.memory.buffer);
  let t = 0;
  for (let i = 0; i < n; i++) t += m[(iovs + i * 8 + 4) / 4];
  m[nw / 4] = t;
  return 0;
};
const imports = {
  env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
  wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write: fdWrite, fd_seek() { return 0; } },
};
const x = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(wasmPath)), imports).exports;
const U32 = () => new Uint32Array(x.memory.buffer);
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const run = (va, a, xs = []) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), BigInt(a[2] ?? 0), BigInt(a[3] ?? 0), BigInt(xs[0] ?? 0), BigInt(xs[1] ?? 0), BigInt(xs[2] ?? 0), BigInt(xs[3] ?? 0)));

x.__wasm_call_ctors(); x.ott_data_install();
U32()[BUD / 4] = 2000000000;
let trap = null;
for (let i = 0; i < 146; i++) {
  const s = slot(i);
  if (i === 0) { U32()[LOG / 4] = 0; U32()[LOG / 4 + 1] = 0; U32()[LOG / 4 + 2] = 0; }
  try { run(0x18011d400, [s.obj, 0]); } catch (e) { trap = { k: i + 1, err: String(e) }; break; }
  for (let p = 0; p < 19; p++) run(0x180120af0, [s.obj, p], [0, 0, f32b(0.5)]);
  run(0x180120800, [s.obj]);
  const F32 = new Float32Array(x.memory.buffer);
  for (let k = 0; k < N * 2; k++) F32[s.buf / 4 + k] = Math.fround(Math.sin(k * 0.05) * 0.5);
  const u = U32();
  u[s.inA / 4] = s.buf; u[s.inA / 4 + 2] = s.buf + N * 4; u[s.ouA / 4] = s.buf + N * 8; u[s.ouA / 4 + 2] = s.buf + N * 12;
}
const u = U32();
const hits = u[LOG / 4], dest = u[LOG / 4 + 1], n = u[LOG / 4 + 2];
console.log(JSON.stringify({
  trap,
  overlap_hits: hits,
  first_overlap: hits ? { dest: '0x' + dest.toString(16), n, vtable_rel: dest - VT, end: '0x' + (dest + n).toString(16) } : null,
  vt_head: '0x' + u[VT / 4].toString(16),
}));
