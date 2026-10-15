// trap56_probe_942.mjs: probe_alloca_942.py の変種で survey と同じ呼び出しを行い、trap の瞬間の記録を読む (#942 受入 1・2, 診断用)。
// 使い方: python3 probe_alloca_942.py <alloca.ll> work/probe_alloca.ll && bash stage4.sh work/probe_alloca.ll probe_alloca
//         S4_NAME=probe_alloca S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap56_probe_942.mjs
// slot 0 (+0 hits) = function_8c7450 の直近 32 回の呼出しの ring (PB+0x100・48 byte: +0 idx・+8 [obj+20]・+16 [obj+8]・+24 戻り値・+32 hit 番号・+40 obj)。
// slot 1 = function_8c6530 (+8/+16/+24 = arg1..3)。elem = [obj+8] + 8*sext32(idx) は function_8c7450 の IR から導く (実測ではない)。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'probe_alloca');
const PROBE_BASE = 0x11FFF600;
const SLOT = 64;
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const RING = 0x100, RN = 32, RS = 48;
const clr = () => mod.HEAPU8.fill(0, PROBE_BASE, PROBE_BASE + RING + RN * RS);
const hx = (v) => '0x' + BigInt.asUintN(64, v).toString(16);
const read = () => {
  const dv = new DataView(mod.HEAPU8.buffer, PROBE_BASE, RING + RN * RS);
  const g = (o) => dv.getBigUint64(o, true);
  const hits = Number(g(0));
  const ring = [];
  for (let j = 0; j < RN; j++) {
    const o = RING + j * RS;
    const n = Number(g(o + 32));
    if (n >= hits || n < 0) continue;
    const idx = BigInt.asIntN(32, g(o));
    ring.push({ n, idx: Number(idx), cnt: Number(g(o + 8)), base: hx(g(o + 16)), ret: hx(g(o + 24)), obj: hx(g(o + 40)), elem: hx(g(o + 16) + idx * 8n) });
  }
  ring.sort((a, b) => a.n - b.n);
  const s1 = { hits: Number(g(SLOT)), a1: hx(g(SLOT + 8)), a2: hx(g(SLOT + 16)), a3: hx(g(SLOT + 24)) };
  return { c8c7450_hits: hits, ring, s1 };
};
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const out = [];
for (let i = 0; i < 942; i++) {
  clr();
  try { mod._m11_call_unit(i); } catch (e) {
    if (!(e && e.m11_dllmain_done !== undefined)) {
      out.push({ i, va: '0x' + Number(mod._m11_unit_va(i)).toString(16), kind: ((e && e.message) || String(e)).split('\n')[0], ...read() });
    }
    mod.__emscripten_stack_restore(sp0);
  }
}
console.log('TRAP56_PROBE ' + JSON.stringify({ units: out }));
