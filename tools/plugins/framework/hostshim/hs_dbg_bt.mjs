// hs_dbg_bt.mjs — CAB-195: wasm trap の完全メッセージ/スタックトレースを取る。
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve as pathResolve } from 'node:path';
const [, , IMG, CJS] = process.argv;
const img = readFileSync(IMG);
const req = createRequire(import.meta.url);
const mod = await req(pathResolve(CJS))();
mod.HEAPU8.set(img, 0x400000);
for (let o = 0; o < 0x100; o++) mod.HEAPU8[0x8a1000 + o] = 0;
try { console.error('[dbg] status=0x' + Number(mod._hs_e2e_run()).toString(16)); }
catch (e) {
  console.error('[dbg] EXC NAME: ' + e.name);
  console.error('[dbg] EXC MSG: ' + e.message);
  console.error('[dbg] EXC STACK:\n' + (e.stack || '(no stack)'));
  // 最後に記録された wasm 入口
}
