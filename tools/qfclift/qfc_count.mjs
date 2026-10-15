// qfc_count.mjs — DllMain 経路の import 呼出し計数 (T-SH-78 / #3411)。qfc_count.sh が呼ぶ。測定専用で判定は行わない。
//   env: QFC_CJS (gen_count_wrap.py で作った計数版 wasm の .cjs) / QFC_CALL_LOG (stderr の [fle] 行を全件追記する先)
// DllMain(PROCESS_ATTACH) → FontCache_GetStats → FontCache_CleanUp と同じ段で実行し、段の戻りと trap を同じ log に残す。
import { appendFileSync, writeFileSync } from 'node:fs';

const log = process.env.QFC_CALL_LOG;
writeFileSync(log, '');
const mod = await import(process.env.QFC_CJS);
const m = await mod.default({ printErr: (s) => { if (s.includes('[fle]')) appendFileSync(log, s + '\n'); }, print: () => {} });
m._fle_data_install();
m._fle_init();
const buf = m._malloc(0x1000);
const steps = [
  ['DllMain', 0x59c1f0, [0x400000, 1, 0]],
  ['FontCache_GetStats', 0x57faf0, [buf]],
  ['FontCache_CleanUp', 0x57f980, []],
];
for (const [name, va, args] of steps) {
  appendFileSync(log, '[step] ' + name + '\n');
  try {
    const r = m._fle_run(va, ...[...args, 0, 0, 0, 0, 0, 0, 0, 0].slice(0, 8).map((x) => BigInt(x)));
    appendFileSync(log, '[ret] ' + name + ' 0x' + BigInt.asUintN(64, BigInt(r)).toString(16) + '\n');
  } catch (e) {
    appendFileSync(log, '[trap] ' + name + ' ' + String(e).slice(0, 120) + '\n');
    break;
  }
}
