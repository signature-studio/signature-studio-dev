// #5695: e3ef60 の arg1 (既定 0x12ba808) の +0x778・+0x7d8・+0x810・+0x808・+0x7f0 が, survey と同順の unit 実行中にいつ変わるかを見る。
// 出力: 各 unit の前後で値が変わった (field, unit, before -> after) と, 対象 unit (既定 895) の前後値。
// 命令番地 (書込み元) は取れない (JS 側の観測のみ)。書込み元の特定は IR 計装が要る (REPORT.md §5 の次の一手)。
// 使い方: node trap_triage/probe5695_arg1.mjs [arg1(16進, 既定 12ba808)] [--target 895]
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const args = process.argv.slice(2);
const arg1 = parseInt(args.find((a) => /^[0-9a-f]+$/i.test(a) && a !== args[args.indexOf('--target') + 1]) ?? '12ba808', 16);
const ti = args.indexOf('--target');
const target = ti >= 0 ? Number(args[ti + 1]) : 895;
const FIELDS = [0x778, 0x7d8, 0x810, 0x808, 0x7f0];
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
const dv = () => new DataView(mod.HEAPU8.buffer);
const snap = () => FIELDS.map((o) => dv().getUint32(arg1 + o, true));
const hex = (x) => '0x' + (x >>> 0).toString(16);
const run = (i) => { try { mod._m11_call_unit(i); return 'ok'; } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
console.log('arg1=' + hex(arg1), 'initial=', snap().map(hex).join(' '));
let prev = snap();
for (let i = 0; i < 942; i++) {
  const before = snap();
  const r = run(i);
  const cur = snap();
  cur.forEach((v, k) => { if (v !== before[k]) console.log('change unit', i, 'result', r, 'field', hex(FIELDS[k]), hex(before[k]), '->', hex(v)); });
  if (i === target) console.log('target unit', i, 'result', r, 'before', before.map(hex).join(' '), 'after', cur.map(hex).join(' '));
  prev = cur;
}
console.log('final=', prev.map(hex).join(' '));
