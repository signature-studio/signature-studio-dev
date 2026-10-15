// PERF-P26 (#4392): 同一 instance で ctor (0x18011d400) を M 回呼ぶ。RESTORE=1 のとき、各 ctor の直前に
// data 領域 (0x301e2000〜0x30284124) を ott_data_install 直後の内容へ戻す。
// 戻して 146 が返るなら「data の書き換えが停止の原因」と整合する。戻しても止まれば、その仮説は支持されない。
// 注意: data 領域には allocator のメタデータも重なるため、戻し後の結果は書き換え有無の切り分けに限る。
// 素材展開後に実行: RESTORE=1 timeout 60 node tools/perf/p15/ctor_restore_data.mjs 146
import fs from 'node:fs'; import path from 'node:path'; import crypto from 'node:crypto'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const WASM = process.env.WASM || path.join(HERE, '../../ott/work/lift/ottl.wasm');
const M = +(process.argv[2] || 146);
const RESTORE = process.env.RESTORE === '1';
const imports = {
  env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
  wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
};
const x = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(WASM)), imports).exports;
x.__wasm_call_ctors(); x.ott_data_install();
const DATA0 = 0x301e2000, DATA1 = 0x30284000 + 292;
const OBJ0 = 0x31000000, STRIDE = 0x40000;
const run = (va, a) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), 0n, 0n, 0n, 0n, 0n, 0n));
const dataView = () => new Uint8Array(x.memory.buffer, DATA0, DATA1 - DATA0);
const hashData = () => crypto.createHash('sha1').update(dataView()).digest('hex').slice(0, 12);
const pristine = Uint8Array.from(dataView());
let changedAt = -1, prev = hashData(), done = 0;
for (let i = 0; i < M; i++) {
  if (RESTORE) dataView().set(pristine);
  run(0x18011d400, [OBJ0 + i * STRIDE, 0]);
  done = i + 1;
  const hd = hashData();
  if (hd !== prev && changedAt < 0) changedAt = i;
  prev = hd;
}
console.log(JSON.stringify({ M, RESTORE, ctor_returned: done, data_changed_during_ctor_at: changedAt, data_hash_end: prev }));
