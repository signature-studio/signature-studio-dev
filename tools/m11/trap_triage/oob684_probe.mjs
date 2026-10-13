// #684: 単発 OOB unit の直前状態を実測する (survey_units.mjs と同じ順序で unit を実行する)
// 使い方: node trap_triage/oob684_probe.mjs <target unit> <addr,...> [watch]
//   既定: target unit の直前に各 addr の u64 を表示し, target を 1 回実行して結果を出す
//   watch: unit 0..target-1 を順に実行し, addr の u64 が変化した unit を表示する (値の最初の書込み元の特定)
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const target = Number(process.argv[2]);
const addrs = process.argv[3].split(',').map(Number);
const watch = process.argv[4] === 'watch';
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
const u64 = (a) => new DataView(mod.HEAPU8.buffer).getBigUint64(a, true).toString(16);
const snap = () => addrs.map((a) => u64(a));
const show = (tag) => console.log(tag, addrs.map((a, k) => a + ':0x' + snap()[k]).join(' '));
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
if (watch) {
  let prev = snap();
  for (let i = 0; i < target; i++) {
    const r = run(i); const cur = snap();
    if (cur.join() !== prev.join()) console.log('unit', i, 'result', r, 'changed', addrs.map((a, k) => a + ':0x' + prev[k] + '->0x' + cur[k]).join(' '));
    prev = cur;
  }
} else {
  for (let i = 0; i < target; i++) run(i);
  show('before unit ' + target + ':');
  const r = run(target);
  console.log('unit', target, 'result', r);
}
