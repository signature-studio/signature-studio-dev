// PERF-P28 (#5403): ctor (0x18011d400) を同一 instance で M 回呼ぶとき、sbrk 相当 (wasm func 123) の break 値
// (線形メモリの番地 269004816 = 0x1008AFD0 の i32) を ctor ごとに記録する。
// malloc を挟まずに直接メモリを読むため、割り当て順は変わらない。
// 素材展開後に実行: node tools/perf/p15/ctor_brk_trace.mjs <wasm> [M=146] [shiftBytes=0]
// shiftBytes は起動直後に malloc で break を押し上げる対照実験 (break が image に届く回を早める)。
// 出力は 1 行 JSON。trap したら trap 情報を残す。
import fs from 'node:fs';
const wasmPath = process.argv[2];
const M = +(process.argv[3] || 146);
const SHIFT = +(process.argv[4] || 0);
const BRK = 269004816, BUD = 0x35F80000;
const OBJ0 = 0x31000000, STRIDE = 0x40000, IMG0 = 0x30000000, IMG_END = 0x30284124;
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
const hex = (v) => '0x' + v.toString(16);
const run = (va, a) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), 0n, 0n, 0n, 0n, 0n, 0n));
x.__wasm_call_ctors(); x.ott_data_install();
new Uint32Array(x.memory.buffer)[BUD / 4] = 2000000000;
if (SHIFT) x.malloc(SHIFT);
const rows = [];
let trap = null;
const h0 = U32()[BRK / 4] >>> 0;
for (let i = 0; i < M; i++) {
  try { run(0x18011d400, [OBJ0 + i * STRIDE, 0]); } catch (e) { trap = { k: i + 1, err: String(e) }; break; }
  const b = U32()[BRK / 4] >>> 0;
  rows.push({ k: i + 1, brk: b });
}
const brkEnd = U32()[BRK / 4] >>> 0;
const inImage = rows.filter((r) => r.brk >= IMG0 && r.brk < IMG_END).map((r) => r.k);
const d = rows.slice(1).map((r, j) => r.brk - rows[j].brk);
const mono = d.every((v) => v >= 0);
console.log(JSON.stringify({
  M, shift: SHIFT, completed: rows.length, trap,
  brk_start: hex(h0), brk_end: hex(brkEnd),
  image: [hex(IMG0), hex(IMG_END)],
  brk_monotonic: mono, delta_min: Math.min(...d), delta_max: Math.max(...d),
  brk_last_completed: rows.length ? hex(rows[rows.length - 1].brk) : null,
  brk_in_image_ctors: inImage.slice(0, 20),
  tail: rows.slice(-6).map((r) => ({ k: r.k, brk: hex(r.brk) })),
  sample: rows.filter((_, j) => j % 20 === 0).map((r) => ({ k: r.k, brk: hex(r.brk) })),
}));
