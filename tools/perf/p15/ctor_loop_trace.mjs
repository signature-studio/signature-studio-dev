// PERF-P28 (#5403): 同一 instance で ctor を M 回呼び、各 ctor の前後で loop head の実行回数を記録する。
// 入力 wasm は tools/ott/work/lift/ottl.wasm を WAT 経由で計装したもの (loop head ごとに counter、budget が 0 で unreachable)。
//   node tools/perf/p15/ctor_loop_trace.mjs <instrumented.wasm> <M> <out.json>
import fs from 'node:fs';

const [wasmPath, MArg = '146', outPath = '/dev/stdout'] = process.argv.slice(2);
const M = +MArg;
const NLOOP = 209;
const BUD = 0x35f80000, CNT = 0x35f80100;
const OBJ0 = 0x31000000, STRIDE = 0x40000, IN0 = 0x34000000, OU0 = 0x34000080, BUF0 = 0x34100000, N = 128;
const slot = (i) => ({ obj: OBJ0 + i * STRIDE, inA: IN0 + i * 0x100, ouA: OU0 + i * 0x100, buf: BUF0 + i * 0x2000 });
const imports = {
  env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
  wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
};
const x = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(wasmPath)), imports).exports;
const U32 = () => new Uint32Array(x.memory.buffer);
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const run = (va, a, xs = []) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), BigInt(a[2] ?? 0), BigInt(a[3] ?? 0), BigInt(xs[0] ?? 0), BigInt(xs[1] ?? 0), BigInt(xs[2] ?? 0), BigInt(xs[3] ?? 0)));
const snap = () => Array.from(U32().subarray(CNT / 4, CNT / 4 + NLOOP));

x.__wasm_call_ctors(); x.ott_data_install();
U32()[BUD / 4] = 2000000000;
const perCtor = [];
let trapAt = null, err = null;
try {
  for (let i = 0; i < M; i++) {
    const s = slot(i);
    const before = snap();
    run(0x18011d400, [s.obj, 0]);
    perCtor.push({ k: i + 1, delta: snap().map((v, j) => v - before[j]), budget_left: U32()[BUD / 4] });
    for (let p = 0; p < 19; p++) run(0x180120af0, [s.obj, p], [0, 0, f32b(0.5)]);
    run(0x180120800, [s.obj]);
    const F32 = new Float32Array(x.memory.buffer);
    for (let k = 0; k < N * 2; k++) F32[s.buf / 4 + k] = Math.fround(Math.sin(k * 0.05) * 0.5);
    const u = U32();
    u[s.inA / 4] = s.buf; u[s.inA / 4 + 2] = s.buf + N * 4; u[s.ouA / 4] = s.buf + N * 8; u[s.ouA / 4 + 2] = s.buf + N * 12;
  }
} catch (e) {
  err = String(e);
  trapAt = perCtor.length + 1;
}
const partial = snap();
const out = { M, trap_at_ctor: trapAt, error: err, per_ctor_count: perCtor.length, partial_counts_at_trap: partial, perCtor };
fs.writeFileSync(outPath, JSON.stringify(out));
console.log(JSON.stringify({ M, trap_at_ctor: trapAt, error: err, completed: perCtor.length }));
