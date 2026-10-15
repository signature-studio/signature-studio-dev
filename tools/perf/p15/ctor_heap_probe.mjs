// PERF-P26 (#4392): 同一 instance で ctor (0x18011d400) を M 回呼ぶときの wasm heap の進みと、
// 次の確保が image の data 領域 (0x301e2000〜0x30284000+292) に重なるかを測る。
// 素材展開後に実行: node tools/perf/p15/ctor_heap_probe.mjs [M=146] [shiftMiB=0]
// 出力は 1 行 JSON。ctor が戻らない場合は外側の timeout で打ち切る (例: timeout 25 node ...)。
import fs from 'node:fs'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const WASM = path.join(HERE, '../../ott/work/lift/ottl.wasm');
const M = +(process.argv[2] || 146), SHIFT = +(process.argv[3] || 0) * 2 ** 20;
const imports = {
  env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
  wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
};
const x = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(WASM)), imports).exports;
x.__wasm_call_ctors(); x.ott_data_install();
if (SHIFT) x.malloc(SHIFT);
const DATA0 = 0x301e2000, DATA1 = 0x30284000 + 292;
const OBJ0 = 0x31000000, STRIDE = 0x40000;
const run = (va, a) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), 0n, 0n, 0n, 0n, 0n, 0n));
const heapHead = () => Number(x.malloc(0x30));
const h0 = heapHead();
const rows = [];
for (let i = 0; i < M; i++) {
  if (i === M - 1) { const h = heapHead(); console.log(JSON.stringify({ before_call: i, heap_head: h.toString(16), next_span_overlaps_data: h + 3673848 > DATA0 && h < DATA1 })); }
  run(0x18011d400, [OBJ0 + i * STRIDE, 0]);
  rows.push(i);
}
const h1 = heapHead();
console.log(JSON.stringify({ M, shift_mib: SHIFT / 2 ** 20, completed: rows.length, heap_start: h0.toString(16), heap_end: h1.toString(16), bytes_per_ctor: Math.round((h1 - h0) / Math.max(1, rows.length)), data_range: [DATA0.toString(16), DATA1.toString(16)] }));
