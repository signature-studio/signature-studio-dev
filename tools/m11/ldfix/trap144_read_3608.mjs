// trap144_read_3608.mjs: trap144_probe_3608.py の変種 (stage4 ビルド済み) を survey と同じ呼び出しで走らせ、
// trap した unit ごとに entry 引数 (5 関数) と、宛先 0x10aa13f0・0x10aa1418 への最後の書込み元 (site id・格納値) を出す (#3608 受入 1・診断用)。
// 使い方: S4_NAME=t144 S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap144_read_3608.mjs > out.txt
//   出力は 1 行 'TRAP144_READ {...}' の JSON。site id は work/t144/sites.json の stores[sid-1] (sid は 1 始まり)。
// 注: 書込み元は「その unit の trap までの最後の一致 store」。一致が無ければ site は null。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 't144');
const PROBE = {
  ENTRY_BASE: 0x11FF9000, ESLOT: 64, W_REC: 0x11FF8000,
  ENTRY: ['function_44aeb0', 'function_44f040', 'function_653660', 'function_412e40', 'function_6539e0'],
  ARGS: [2, 3, 4, 2, 3],
  WATCH: { A: 0x10aa13f0, B: 0x10aa1418 },
};
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const hx = (v) => '0x' + BigInt.asUintN(64, v).toString(16);
const clr = () => {
  mod.HEAPU8.fill(0, PROBE.ENTRY_BASE, PROBE.ENTRY_BASE + 5 * PROBE.ESLOT);
  mod.HEAPU8.fill(0, PROBE.W_REC, PROBE.W_REC + 24);
};
const read = () => {
  const dv = new DataView(mod.HEAPU8.buffer);
  const entries = PROBE.ENTRY.map((fn, k) => {
    const base = PROBE.ENTRY_BASE + k * PROBE.ESLOT;
    const hits = dv.getBigUint64(base, true);
    const args = [];
    for (let a = 1; a <= PROBE.ARGS[k]; a++) args.push(hx(dv.getBigUint64(base + 8 * a, true)));
    return { fn, hits: Number(hits), args };
  });
  const addr = dv.getBigUint64(PROBE.W_REC, true);
  const sid = dv.getBigUint64(PROBE.W_REC + 8, true);
  const val = dv.getBigUint64(PROBE.W_REC + 16, true);
  const watched = addr === 0n ? null : {
    addr: hx(addr),
    which: addr === BigInt(PROBE.WATCH.A) ? 'A' : addr === BigInt(PROBE.WATCH.B) ? 'B' : '?',
    sid: Number(sid),
    val: hx(val),
  };
  return { entries, last_store_to_watch: watched };
};
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
clr();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const out = [];
for (let i = 0; i < 942; i++) {
  clr();
  try { mod._m11_call_unit(i); } catch (e) {
    if (!(e && e.m11_dllmain_done !== undefined)) {
      const kind = ((e && e.message) || String(e)).split('\n')[0];
      const chain = e && e.stack ? [...String(e.stack).matchAll(/wasm-function\[(\d+)\]:(0x[0-9a-f]+)/g)].slice(0, 6).map(c => [+c[1], c[2]]) : [];
      out.push({ i, va: hx(BigInt(mod._m11_unit_va(i))), kind, chain, ...read() });
    }
    mod.__emscripten_stack_restore(sp0);
  }
}
console.log('TRAP144_READ ' + JSON.stringify({ units: out }));
