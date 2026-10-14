// hs_preinit.mjs — #2008 診断: hs_route.cjs (hostfix 適用ビルド) で DllMain(attach) を先に走らせ、
// InitUnits がどの unit で止まるかと RTL 例外フック 3 変数 (0x710030/0x710038/0x710040) の値を出す。
// その後に Phase B (hs_e2e_run) を同一 instance で実行する。判定はしない (観測専用・hs_e2e.sh には組み込まない)。
//
// 使い方: node hs_preinit.mjs <work>/fw_image.bin <work>/hs_route.cjs   (hs_e2e.sh 実行後の work/hs で)
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve as pathResolve } from 'node:path';

const [, , IMG, CJS] = process.argv;
if (!IMG || !CJS) { console.error('usage: node hs_preinit.mjs <fw_image.bin> <hs_route.cjs>'); process.exit(2); }
const mod = await createRequire(import.meta.url)(pathResolve(CJS))();
mod.HEAPU8.set(readFileSync(IMG), 0x400000);
for (let o = 0; o < 0x100; o++) mod.HEAPU8[0x8a1000 + o] = 0;
Error.stackTraceLimit = 40;

const INIT_TABLE_GV = 0x714c90, UNIT_COUNTER_GV = 0x714c98;
const dv = () => new DataView(mod.HEAPU8.buffer);
const q = (va) => '0x' + dv().getBigUint64(va, true).toString(16);

try {
  mod._function_6c13a0(0x400000n, 1n, 0n, 0n);
  console.error('[pre] DllMain returned (InitUnits 完走)');
} catch (e) {
  console.error('[pre] DllMain 例外: %s', (e.message || '').split('\n')[0]);
  console.error((e.stack || '').split('\n').slice(1, 12).join('\n'));
}
const d = dv();
const tbl = Number(d.getBigUint64(INIT_TABLE_GV, true));
console.error('[pre] unit counter(0x714c98)=%d / InitTable 総数=%d', d.getInt32(UNIT_COUNTER_GV, true), tbl ? d.getUint32(tbl, true) : -1);
console.error('[pre] [0x710030]=%s [0x710038]=%s [0x710040]=%s', q(0x710030), q(0x710038), q(0x710040));

let st = -1;
try { st = Number(mod._hs_e2e_run()); } catch (e) { console.error('[pre] Phase B 例外: %s', (e.message || '').split('\n')[0]); }
console.error('[pre] Phase B: status=0x%s plug=0x%s rec=%d', (st >>> 0).toString(16),
  Number(mod._hs_plug_get()).toString(16), Number(mod._fw_hs_count()));
