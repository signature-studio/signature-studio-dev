// M11 unit probe (#516): m11_survey.mjs と同手順で 942 unit を順に実行し, M11_PROBE_UNITS (カンマ区切り idx) の結果と trap スタックを出す.
// 使い方: M11_PROBE_UNITS=87,898 [M11_PROBE_SKIP=101,144] [M11_BOOT=<m11_boot.cjs>] node tools/m11/qstore/unit_probe.mjs
//   (既定 work/m11_boot.cjs; state 依存なので idx 0 から通し実行する。SKIP は survey の OOM/InitTable 破壊 unit を飛ばす (#513))
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const probe = new Set((process.env.M11_PROBE_UNITS || '').split(',').filter(Boolean).map(Number));
const skip = new Set((process.env.M11_PROBE_SKIP || '').split(',').filter(Boolean).map(Number));
const m2 = await import(process.env.M11_BOOT || (M11 + '/work/m11_boot.cjs'));
const errs = [];
const mod = await m2.default({ printErr: (s) => { errs.push(String(s)); } });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const lim = Math.max(...probe, -1);
for (let i = 0; i <= lim; i++) {
  if (skip.has(i)) continue;
  const e0 = errs.length;
  let res;
  try { const r = mod._m11_call_unit(i); res = r === 1 ? 'ok' : r === 0 ? 'noproc' : r === 2 ? 'miss' : 'r' + r; }
  catch (e) {
    res = 'trap: ' + (e && e.m11_dllmain_done !== undefined ? 'halt0->longjmp' : ((e && e.message) || String(e)).split('\n')[0]);
    if (probe.has(i)) res += '\n' + String((e && e.stack) || '').split('\n').slice(0, 8).join('\n');
    mod.__emscripten_stack_restore(sp0);
  }
  if (probe.has(i)) {
    console.log(`unit ${i} VA 0x${mod._m11_unit_va(i).toString(16)}: ${res}`);
    for (const l of errs.slice(e0, e0 + 12)) console.log('  stderr: ' + l.slice(0, 200));
  }
}
