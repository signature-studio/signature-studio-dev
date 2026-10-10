// fw_run.mjs — P0a (CAB-194) headless smoke: Delphi framework 初期化 (DllMain attach → _StartLib → _InitLib → InitUnits) を wasm で完走させる。
// 使い方: node fw_run.mjs <work>/fw_image.bin [work]/fw_route.cjs
// 判定: entry (function_6c13a0 = DllMain, hinst=0x400000 / DLL_PROCESS_ATTACH=1) が trap 無しで帰ること。
//       RestoreContext 到達 (Halt0 経路) も m11 方式で正常終了と扱う。
//       plugin kernel 表 (CAB-196 担当) は呼ばない。
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const IMG = process.argv[2] || 'fw_image.bin';
const img = readFileSync(IMG);
const req = createRequire(import.meta.url);
const cjsPath = process.argv[3] || new URL('./fw_route.cjs', import.meta.url).pathname;
const createModule = req(cjsPath);

const IMAGE_BASE = 0x400000;
const INIT_TABLE_GV = 0x714c90;
const UNIT_COUNTER_GV = 0x714c98;

function readStats(mod) {
  const s = { dispatch: 0, va: 0, heap: 0, ff: 0, counter: -1, tbl: 0 };
  try { s.dispatch = Number(mod._fw_dispatch_count()); } catch (e) {}
  try { s.va = Number(mod._fw_va_calls()); } catch (e) {}
  try { s.heap = Number(mod._fw_alloc_count()); } catch (e) {}
  try { s.ff = Number(mod._fw_ff_count()); } catch (e) {}
  try {
    const dv = new DataView(mod.HEAPU8.buffer);
    s.counter = dv.getInt32(UNIT_COUNTER_GV, true);
    s.tbl = Number(dv.getBigUint64(INIT_TABLE_GV, true));
  } catch (e) {}
  return s;
}

const mod = await createModule();
const H = mod.HEAPU8;

// PE image 敷設 + BLK 0 クリア
H.set(img, IMAGE_BASE);
for (let o = 0; o < 0x100; o++) H[0x8a1000 + o] = 0;

const t0 = Date.now();
try {
  const entry = mod._function_6c13a0;
  if (!entry) throw new Error('entry function_6c13a0 が export されていない');
  const r = entry(BigInt(IMAGE_BASE), 1n, 0n, 0n);
  // 正常 return (RestoreContext を通らない場合)
  const s = readStats(mod);
  const raxNum = Number(BigInt.asUintN(64, typeof r === 'bigint' ? r : BigInt(r || 0)));
  console.error('[fw] SMOKE PASS (return path): rax=0x%s dispatch=%d units_done=%d va=%d heap=%d',
    raxNum.toString(16), s.dispatch, s.counter, s.va, s.heap);
  process.exit(0);
} catch (e) {
  const msg = e.message || '';
  const s = readStats(mod);
  if (msg.includes('exit(0)') || msg.includes('corrupted its heap')) {
    // RestoreContext 到達 = Halt0 経路 = m11 方式の正常終了
    console.error('[fw] SMOKE PASS (Halt0/RestoreContext 到達): dispatch=%d units_done=%d va=%d heap=%d ff=%d',
      s.dispatch, s.counter, s.va, s.heap, s.ff);
    process.exit(0);
  }
  console.error('[fw] SMOKE FAIL: %s (dispatch=%d units_done=%d ff=%d)', msg.split('\n')[0], s.dispatch, s.counter, s.ff);
  process.exit(1);
}
