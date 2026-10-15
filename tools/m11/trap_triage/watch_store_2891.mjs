// #2891: store 計装版 (wasm-opt --instrument-memory、trap_2891/instr.wasm) で、監視番地 WATCH_W (8B) と重なる全 store を
// unit 単位で記録する (WATCH_OLD のような絞りは無い)。hook は JS import で線形メモリには書かない (挙動を変えない)。
// 記録: unit・store 計装 id (sites.json で wat の関数・行に戻す)・実効アドレス・bytes・store 直前の 8B (old8)・書込み値 (val)・wasm frame。
// 併せて unit 別 kind を出し、survey_units.mjs の kind と一致することを確かめる (陰性対照)。
// frame の取得は重い (全 hit で new Error().stack) ので WATCH_LOG_UNITS で記録する unit を絞る。hit 件数は全 unit で数える。
// 使い方: node watch_store_2891.mjs <out.json> (環境変数 WATCH_W (既定 0x10aa1430) / WATCH_WASM / WATCH_UNITS / WATCH_LOG_UNITS / WATCH_LOG_MAX)
import fs from 'fs';
Error.stackTraceLimit = 40;
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const W = Number(process.env.WATCH_W || '0x10aa1430');
const INSTR = process.env.WATCH_WASM || M11 + '/work/trap_2891/instr.wasm';
const LOG_MAX = Number(process.env.WATCH_LOG_MAX || 400);
const UNITS = process.env.WATCH_UNITS ? process.env.WATCH_UNITS.split(',').map(Number) : Array.from({ length: 942 }, (_, i) => i);
const LOG = process.env.WATCH_LOG_UNITS ? new Set(process.env.WATCH_LOG_UNITS.split(',').map(Number)) : null;
let curUnit = -1, hitN = 0, mem = null, pend = null;
const hits = [];
const wasmFrames = () => ((new Error().stack) || '').split('\n').filter(l => /wasm-function/.test(l)).slice(0, 6).map(l => l.trim().replace(/^at /, ''));
const read8 = (a) => { const dv = new DataView(mem.buffer); return (BigInt(dv.getUint32(a + 4, true)) << 32n) | BigInt(dv.getUint32(a, true)); };
const hex = (v) => '0x' + BigInt.asUintN(64, BigInt(v)).toString(16);
const storePtr = (id, nbytes, off, ptr) => {
  if (mem === null) return ptr;
  const a = (ptr >>> 0) + (off >>> 0);
  if (a < W + 8 && a + nbytes > W) {
    hitN++;
    const logged = LOG === null || LOG.has(curUnit);
    pend = { id, rec: { unit: curUnit, id, addr: '0x' + a.toString(16), bytes: nbytes, old8: hex(read8(W)), frames: logged ? wasmFrames() : null } };
    if (logged && hits.length < LOG_MAX) hits.push(pend.rec);
  }
  return ptr;
};
const storeVal32 = (id, v) => { if (pend && pend.id === id) { pend.rec.val = hex(v >>> 0); pend = null; } return v; };
const storeVal64 = (id, v) => { if (pend && pend.id === id) { pend.rec.val = hex(v); pend = null; } return v; };
const pass2 = (_id, v) => v;
const hooks = {
  store_ptr: storePtr, load_ptr: (_id, _n, _off, ptr) => ptr,
  store_val_i32: storeVal32, store_val_i64: storeVal64, store_val_f32: pass2, store_val_f64: pass2,
  load_val_i32: pass2, load_val_i64: pass2, load_val_f32: pass2, load_val_f64: pass2,
  memory_grow_pre: (_a, b) => b, memory_grow_post: (_a, b) => b,
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
const kinds = {}, per = [];
const t0 = Date.now();
for (const i of UNITS) {
  curUnit = i;
  const rec = { unit: i };
  const hit0 = hitN;
  try {
    const r = mod._m11_call_unit(i);
    rec.kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss';
  } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) rec.kind = 'halt0';
    else {
      const msg = ((e && e.message) || String(e)).split('\n')[0];
      rec.kind = /out of bounds/.test(msg) && !/table/.test(msg) ? 'oob' : /abort/i.test(msg) ? 'abort' : 'other';
    }
    mod.__emscripten_stack_restore(sp0);
  }
  if (hitN > hit0) rec.hits = hitN - hit0;
  kinds[rec.kind] = (kinds[rec.kind] || 0) + 1;
  per.push(rec);
}
fs.writeFileSync(process.argv[2], JSON.stringify({ W: '0x' + W.toString(16), hitN, hits, per }, null, 1));
console.log('WATCH2891 ' + JSON.stringify(kinds) + ' hits=' + hitN + ' sec=' + ((Date.now() - t0) / 1000).toFixed(1));
