// hs_probe_40c4.mjs — #2534 診断: DllMain(attach) が function_40c4d0 で OOB するときの this を出す。
// 観測専用・判定なし。hs_preinit.mjs と同じ手順で DllMain を 1 回だけ走らせ、例外後に次を出す。
//   [0x7165b8]: function_43b130 が call function_40c4d0 の前に rcx として読む this (0 なら VMT 読みが境界外)
//   [0x8a1008]: BLK+0x08 (fix_40c4d0 が rcx に読む caller 格納値)
//   [0]:        this=0 のときに [rcx] として読まれる値 (参考)
//
// 使い方: node hs_probe_40c4.mjs <work>/fw_image.bin <work>/hs_route.cjs   (hs_e2e.sh --fresh 実行後の work/hs で)
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve as pathResolve } from 'node:path';

const [, , IMG, CJS] = process.argv;
if (!IMG || !CJS) { console.error('usage: node hs_probe_40c4.mjs <fw_image.bin> <hs_route.cjs>'); process.exit(2); }
const mod = await createRequire(import.meta.url)(pathResolve(CJS))();
mod.HEAPU8.set(readFileSync(IMG), 0x400000);
for (let o = 0; o < 0x100; o++) mod.HEAPU8[0x8a1000 + o] = 0;
Error.stackTraceLimit = 40;

const UNIT_COUNTER_GV = 0x714c98, THIS_SLOT = 0x7165b8, BLK_HOST = 0x8a1008;
const dv = () => new DataView(mod.HEAPU8.buffer);
const u64 = (va) => (va + 8 <= mod.HEAPU8.length ? dv().getBigUint64(va, true) : -1n);
const hex = (v) => '0x' + v.toString(16);

try {
  mod._function_6c13a0(0x400000n, 1n, 0n, 0n);
  console.error('[probe] DllMain returned (InitUnits 完走)');
} catch (e) {
  console.error('[probe] DllMain 例外: %s', (e.message || '').split('\n')[0]);
  console.error((e.stack || '').split('\n').slice(1, 8).join('\n'));
}
console.error('[probe] unit counter(0x714c98)=%d', dv().getInt32(UNIT_COUNTER_GV, true));
console.error('[probe] [0x7165b8]=%s (function_40c4d0 の this)', hex(u64(THIS_SLOT)));
console.error('[probe] [0x8a1008]=%s (BLK+0x08)', hex(u64(BLK_HOST)));
const thisv = u64(THIS_SLOT);
const vt = u64(Number(thisv));
const off = Number(vt) - 0x80;
console.error('[probe] [this]=%s (VMT 候補)', hex(vt));
console.error('[probe] [vt-0x80]: アドレス %d (範囲内=%s, memory=0x%s)', off, off >= 0 && off + 4 <= mod.HEAPU8.length, mod.HEAPU8.length.toString(16));
