// PERF-P28 (#5403): instr_calls.py で計装した wasm を使い、vtable (0x30203BD0) 先頭語が 0 になった最初の call 戻りの前後の呼び出し列を出す。
// 出力: 検出時点の前後 K 件を site id と (caller → callee) で並べる。
//   node tools/perf/p15/ctor_call_window.mjs <instrumented.wasm> <sites.json> [K]
import fs from 'node:fs';

const [wasmPath, sitesPath, kArg] = process.argv.slice(2);
const K = Number(kArg ?? 40);
const sites = JSON.parse(fs.readFileSync(sitesPath, 'utf8'));
const OBJ0 = 0x31000000, STRIDE = 0x40000, IN0 = 0x34000000, OU0 = 0x34000080, BUF0 = 0x34100000, N = 128;
const DET = 0x35F81004, CNT = 0x35F81008, RING = 0x35F82000, BUD = 0x35F80000;
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
  if (i === 145) { U32()[CNT / 4] = 0; U32()[DET / 4] = 0; }
  try { run(0x18011d400, [s.obj, 0]); } catch (e) { trap = { k: i + 1, err: String(e) }; break; }
  for (let p = 0; p < 19; p++) run(0x180120af0, [s.obj, p], [0, 0, f32b(0.5)]);
  run(0x180120800, [s.obj]);
  const F32 = new Float32Array(x.memory.buffer);
  for (let k = 0; k < N * 2; k++) F32[s.buf / 4 + k] = Math.fround(Math.sin(k * 0.05) * 0.5);
  const u = U32();
  u[s.inA / 4] = s.buf; u[s.inA / 4 + 2] = s.buf + N * 4; u[s.ouA / 4] = s.buf + N * 8; u[s.ouA / 4 + 2] = s.buf + N * 12;
}
const u = U32();
const cnt = u[CNT / 4], det = u[DET / 4];
const ringAt = (j) => u[(RING + (j & 1023) * 4) / 4];
const name = (id) => {
  const s = sites[id];
  return s ? `f${s.caller}->f${s.callee}` : `?${id}`;
};
const rows = [];
for (let j = Math.max(1, det - K); j <= Math.min(cnt, det + 2); j++) {
  const id = ringAt(j);
  rows.push({ n: j, site: id, call: name(id), mark: j === det ? '<== zero first seen' : '' });
}
console.log(JSON.stringify({ trap, entries_in_ctor146: cnt, zero_seen_at_call: det || null }));
for (const r of rows) console.log(`${r.n}\tsite ${r.site}\t${r.call}\t${r.mark}`);
