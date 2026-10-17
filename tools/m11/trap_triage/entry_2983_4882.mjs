// #4882: `$2983` の分岐条件の実行時値を unit 単位で記録する。
// 入力 `$2` (入口で dbg_entry_4882 に渡す) と `*(s+280)` (`$38`・load_val_i64 id 54599) から、wat と同じ式で
// `$8 = ($2 & 0xffff) - 256` と `$15 = ($8 < wrap($38))` (真なら block3 を抜けて call $161 を飛ばす) を求める。
// 使い方: node entry_2983_4882.mjs <out.json> (環境変数 WATCH_UNITS 既定 0..941 を順に実行 / WATCH_LOG_UNIT 既定 492 / WATCH_WASM)
// unit は順に実行する (前 run と同じ状態遷移。単独実行だと unit 492 は oob になる)。記録は WATCH_LOG_UNIT のみ。
import fs from 'fs';
Error.stackTraceLimit = 0;
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const INSTR = process.env.WATCH_WASM || M11 + '/work/trap_2891/instr_entry_4882.wasm';
const UNITS = process.env.WATCH_UNITS ? process.env.WATCH_UNITS.split(',').map(Number) : Array.from({ length: 942 }, (_, i) => i);
const LOG_UNIT = Number(process.env.WATCH_LOG_UNIT || 492);
const LOG_MAX = Number(process.env.WATCH_LOG_MAX || 4000);
const ID_SF = 54599;
let curUnit = -1, mem = null, entryN = 0;
const log = [];
let pendIn = null;
const hex = (v) => '0x' + BigInt.asUintN(64, BigInt(v)).toString(16);
const hooks = {
  store_ptr: (_id, _n, _off, ptr) => ptr,
  load_ptr: (_id, _n, _off, ptr) => ptr,
  store_val_i32: (_id, v) => v, store_val_i64: (_id, v) => v, store_val_f32: (_id, v) => v, store_val_f64: (_id, v) => v,
  load_val_i32: (_id, v) => v,
  load_val_i64: (id, v) => {
    if (id === ID_SF && curUnit === LOG_UNIT && pendIn !== null) { log.push({ unit: curUnit, in2: pendIn, sf280: hex(v) }); pendIn = null; }
    return v;
  },
  load_val_f32: (_id, v) => v, load_val_f64: (_id, v) => v,
  memory_grow_pre: (_a, b) => b, memory_grow_post: (_a, b) => b,
  dbg_entry_4882: (v2) => { if (curUnit === LOG_UNIT) { pendIn = hex(v2 >>> 0); entryN++; } return 0; },
};
const bin = fs.readFileSync(INSTR);
const mod = await m2.default({
  printErr: () => {},
  instantiateWasm: (info, cb) => {
    Object.assign(info.env, hooks);
    const inst = new WebAssembly.Instance(new WebAssembly.Module(bin), info);
    mem = inst.exports.memory;
    cb(inst);
  },
});
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const kinds = {};
for (const i of UNITS) {
  curUnit = i;
  pendIn = null;
  let kind;
  try {
    const r = mod._m11_call_unit(i);
    kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss';
  } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) kind = 'halt0';
    else {
      const msg = ((e && e.message) || String(e)).split('\n')[0];
      kind = /out of bounds/.test(msg) && !/table/.test(msg) ? 'oob' : /abort/i.test(msg) ? 'abort' : 'other';
    }
    mod.__emscripten_stack_restore(sp0);
  }
  kinds[i] = kind;
  curUnit = -1;
}
const rows = log.slice(0, LOG_MAX).map((r) => {
  const in2 = BigInt(r.in2) & 0xffffffffn;
  const b8 = (Number(in2 & 0xffffn) - 256) | 0;
  const sf = BigInt.asIntN(32, BigInt(r.sf280));
  const b15 = b8 < Number(sf);
  return { ...r, b8: b8, ge: !b15, takesCall161: !b15 };
});
const summary = { entryN, calls: log.length, takesCall161: rows.filter((r) => r.takesCall161).length, kindCount: {} };
for (const k of Object.values(kinds)) summary.kindCount[k] = (summary.kindCount[k] || 0) + 1;
fs.writeFileSync(process.argv[2], JSON.stringify({ kinds, summary, rows }, null, 1));
console.log(JSON.stringify({ summary, u492: kinds[LOG_UNIT] }));
