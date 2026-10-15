// PERF-P26 (#4392): 同一 instance で ctor (0x18011d400) を M 回呼んだ後、
//  (a) data 領域 (0x301e2000〜0x30284124) の hash が変わった呼び出し番号、
//  (b) malloc が data 領域に重なる確保を返すか、そのとき data の hash が変わるか、を 1 行 JSON で出す。
// 素材展開後に実行: node tools/perf/p15/ctor_data_overlap.mjs [M=145] (WASM 既定 = ../../ott/work/lift/ottl.wasm)
// M=146 の ctor は戻らない (外側で timeout を付ける)。M=145 で (a) は changed_at=-1 (変化なし) になる。
import fs from 'node:fs'; import path from 'node:path'; import crypto from 'node:crypto'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const WASM = process.env.WASM || path.join(HERE, '../../ott/work/lift/ottl.wasm');
const M = +(process.argv[2] || 145);
const imports = {
  env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
  wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
};
const x = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(WASM)), imports).exports;
x.__wasm_call_ctors(); x.ott_data_install();
const DATA0 = 0x301e2000, DATA1 = 0x30284000 + 292;
const OBJ0 = 0x31000000, STRIDE = 0x40000;
const run = (va, a) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), 0n, 0n, 0n, 0n, 0n, 0n));
const hashData = () => crypto.createHash('sha1').update(new Uint8Array(x.memory.buffer, DATA0, DATA1 - DATA0)).digest('hex').slice(0, 12);
const heapHead = () => Number(x.malloc(0x30));
const hash0 = hashData(), heap0 = heapHead();
let changedAt = -1, prev = hash0;
for (let i = 0; i < M; i++) {
  run(0x18011d400, [OBJ0 + i * STRIDE, 0]);
  const hd = hashData();
  if (hd !== prev && changedAt < 0) changedAt = i;
  prev = hd;
}
const hashAfterCtor = prev;
let overlap = null;
for (let k = 0; k < 400; k++) {
  const before = hashData();
  const p = Number(x.malloc(0x40000));
  if (p === 0) break;
  if (p + 0x40000 > DATA0 && p < DATA1) { overlap = { k, p: p.toString(16), data_hash_before_malloc: before, data_hash_after_malloc: hashData() }; break; }
}
console.log(JSON.stringify({ M, heap_start: heap0.toString(16), data_hash_start: hash0, data_changed_during_ctor_at: changedAt, data_hash_after_ctor: hashAfterCtor, first_malloc_overlap: overlap }));
