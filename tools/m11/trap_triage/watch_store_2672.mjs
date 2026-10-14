// #2672: store 計装版 (wasm-opt --instrument-memory の出力) で、監視番地 WATCH_W と重なる store のうち
// 下位 4B が WATCH_OLD に等しいものを unit 単位で記録する。hook は JS import で、線形メモリには書かない (挙動を変えない)。
// 記録: unit 番号・store 計装 id (sites.json で wat の関数・行に戻す)・実効アドレス・呼出し元の wasm frame。
// 使い方: node watch_store_2672.mjs <out.json> (環境変数 WATCH_W / WATCH_OLD / WATCH_WASM / WATCH_UNITS)
import fs from 'fs';
Error.stackTraceLimit = 40;
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const W = Number(process.env.WATCH_W || '0x10a9f910');
const OLD = Number(process.env.WATCH_OLD || '0x1029e5d8');
const INSTR = process.env.WATCH_WASM || M11 + '/work/trap_2672/instr.wasm';
const LOG_MAX = Number(process.env.WATCH_LOG_MAX || 200);
const UNITS = process.env.WATCH_UNITS ? process.env.WATCH_UNITS.split(',').map(Number) : Array.from({ length: 942 }, (_, i) => i);
let curUnit = -1, hitN = 0, mem = null, pendId = -1;
const hits = [];
const wasmFrames = () => ((new Error().stack) || '').split('\n').filter(l => /wasm-function/.test(l)).slice(0, 6).map(l => l.trim().replace(/^at /, ''));
const storePtr = (id, nbytes, off, ptr) => {
  if (mem === null) return ptr;
  const a = (ptr >>> 0) + (off >>> 0);
  if (a < W + 8 && a + nbytes > W) {
    if (new DataView(mem.buffer).getUint32(W, true) === OLD) {
      hitN++;
      pendId = id;
      if (hits.length < LOG_MAX) hits.push({ unit: curUnit, id, addr: '0x' + a.toString(16), bytes: nbytes, frames: wasmFrames() });
    }
  }
  return ptr;
};
const pass2 = (_id, v) => v;
const storeVal32 = (id, v) => { if (id === pendId) { pendId = -1; if (hits.length) hits[hits.length - 1].val = '0x' + (v >>> 0).toString(16); } return v; };
const hooks = {
  store_ptr: storePtr, load_ptr: (_id, _n, _off, ptr) => ptr,
  store_val_i32: storeVal32, store_val_i64: pass2, store_val_f32: pass2, store_val_f64: pass2,
  load_val_i32: pass2, load_val_i64: pass2, load_val_f32: pass2, load_val_f64: pass2,
  memory_grow_pre: (_a, b) => b, memory_grow_post: (_a, b) => b,
};
const bin = fs.readFileSync(INSTR);
const mod = await m2.default({
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
      rec.msg = msg;
    }
    mod.__emscripten_stack_restore(sp0);
  }
  if (hitN > hit0) rec.hits = hitN - hit0;
  kinds[rec.kind] = (kinds[rec.kind] || 0) + 1;
  per.push(rec);
}
fs.writeFileSync(process.argv[2], JSON.stringify({ W: '0x' + W.toString(16), OLD: '0x' + OLD.toString(16), hitN, hits, per }, null, 1));
console.log('WATCH2672 ' + JSON.stringify(kinds) + ' hits=' + hitN + ' sec=' + ((Date.now() - t0) / 1000).toFixed(1));
