// #2056: unit 158 (0x26d1a0) の ok/trap を分ける先行 unit の状態を切り分ける。
//   dump    <pre-units csv> <out.bin>            boot → 先行 unit を実行した直後の HEAPU8 を書き出す
//   overlay <ranges csv hex lo-hi> <dump.bin>    boot → unit 0 → dump の指定範囲だけ重ね → unit 158
// 前提: work/m11_boot.cjs・work/m11_image.bin 生成済み (m11_build.sh の後)。既定 build (M11_OV_413060=0) で使う。
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const [mode, a1, a2] = process.argv.slice(2);

const boot = async () => {
  const mod = await m2.default({ printErr: () => {} });
  mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
  mod._m11_set_survey(1);
  const sp_boot = mod._emscripten_stack_get_current();
  try { mod._m11_boot_enter(0n, 1n); } catch (e) {
    if (!(e && e.m11_dllmain_done !== undefined)) throw e;
    mod.__emscripten_stack_restore(sp_boot);
  }
  return mod;
};
const callUnit = (mod, sp0, u) => {
  try { const r = mod._m11_call_unit(u); return r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss'; }
  catch (e) { mod.__emscripten_stack_restore(sp0); return 'trap:' + String((e && e.message) || e).split('\n')[0]; }
};

const mod = await boot();
const sp0 = mod._emscripten_stack_get_current();
if (mode === 'dump') {
  for (const u of a1.split(',').filter(Boolean).map(Number)) callUnit(mod, sp0, u);
  fs.writeFileSync(a2, Buffer.from(mod.HEAPU8.buffer, 0, mod.HEAPU8.length));
  console.log('dumped', a2);
} else if (mode === 'overlay') {
  const ranges = a1 === 'none' ? [] : a1.split(',').map(r => r.split('-').map(x => parseInt(x, 16)));
  const src = fs.readFileSync(a2);
  callUnit(mod, sp0, 0);
  for (const [lo, hi] of ranges) mod.HEAPU8.set(src.subarray(lo, hi), lo);
  console.log('overlay', a1, '=>', callUnit(mod, sp0, 158));
} else {
  throw new Error('mode: dump | overlay');
}
