// #2780 計測専用 (M11_PROBE_2780=1 で build した work/m11_boot.cjs が必要): function_4473f0 の各反復の値 (m11_p2780_put) を unit ごとに読む.
// survey_units.mjs と同じ boot・unit 順・trap 後の stack 復元で全 unit を走らせ, unit の kind と記録を JSON に出す.
// usage: node probe_2780_units.mjs <out.json>
import fs from 'fs';
Error.stackTraceLimit = 40;
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const RING = 256;
const readLog = (n0, n1) => {
  const out = [];
  for (let k = n0; k < n1; k++) out.push({ tag: mod._m11_p2780_get(k % RING, 0), v: '0x' + BigInt(mod._m11_p2780_get(k % RING, 1)).toString(16) });
  return out;
};
const all = [], per = [];
for (let i = 0; i < 942; i++) {
  const n0 = mod._m11_p2780_n();
  let kind;
  try {
    const r = mod._m11_call_unit(i);
    kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss';
  } catch (e) {
    const msg = ((e && e.message) || String(e)).split('\n')[0];
    if (e && e.m11_dllmain_done !== undefined) kind = 'halt0';
    else kind = /out of bounds/.test(msg) && !/table/.test(msg) ? 'oob' : /abort/i.test(msg) ? 'abort' : 'other';
    mod.__emscripten_stack_restore(sp0);
  }
  const n1 = mod._m11_p2780_n();
  all.push([i, kind]);
  if (n1 > n0) per.push({ unit: i, kind, n: n1 - n0, log: readLog(Math.max(n0, n1 - RING), n1) });
}
fs.writeFileSync(process.argv[2] || '/dev/stdout', JSON.stringify({ all, per }, null, 1));
const kinds = {}; for (const [, k] of all) kinds[k] = (kinds[k] || 0) + 1;
console.log('PROBE2780_KINDS ' + JSON.stringify(kinds));
console.log('PROBE2780_UNITS_WITH_LOG ' + per.length);
