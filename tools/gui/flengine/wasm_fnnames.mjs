// WIN-14 (#2964): SHIMOPEN の caller を wasm の function index から lift 関数名 (function_<VA>) に解決する。
// name section の無い wasm では V8 のスタックは `wasm-function[N]` (N = function index) しか出さない。
// N → 名前の表は <cjs>.wasm の export section から作る (--export-all で lift 関数は全て export 済み)。build 出力は読むだけで変えない。
//   import { wasmFuncNames, fillCaller } from './wasm_fnnames.mjs';
import fs from 'fs';

const LIFT = /^function_[0-9a-fA-F]+$/;
const WASM_FN = /wasm-function\[(\d+)\]/;

const leb = (b, i) => {
  let r = 0, s = 1, c;
  do { c = b[i++]; r += (c & 0x7f) * s; s *= 128; } while (c & 0x80);
  return [r, i];
};

export function wasmFuncNames(wasmFile) {
  const b = fs.readFileSync(wasmFile);
  const names = new Map();
  let i = 8;
  while (i < b.length) {
    const sid = b[i++];
    let sz;
    [sz, i] = leb(b, i);
    const end = i + sz;
    if (sid === 7) {
      let cnt;
      [cnt, i] = leb(b, i);
      for (let n = 0; n < cnt; n++) {
        let ln;
        [ln, i] = leb(b, i);
        const name = b.toString('utf8', i, i + ln);
        i += ln;
        const kind = b[i++];
        let idx;
        [idx, i] = leb(b, i);
        if (kind === 0 && !names.has(idx)) names.set(idx, name);
      }
    }
    i = end;
  }
  return names;
}

export function fillCaller(rec, names) {
  if (rec.caller) return rec;
  for (const f of rec.frames || []) {
    const m = WASM_FN.exec(f);
    const name = m ? names.get(Number(m[1])) : f;
    if (name && LIFT.test(name)) return { ...rec, caller: name };
  }
  return rec;
}
