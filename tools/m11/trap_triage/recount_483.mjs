// 独立再計算 (#483): survey_diff.py / annotate.py とは別実装 (Node) で survey_units.mjs の 2 出力を再集計する.
//   usage: node recount_483.mjs base.json new.json [unit ...]
//   出力: (1) 種別集計 (2) 遷移 (3) ok 退行 unit (4) new 側 halt0 の Error() 呼出元 (Halt0 鎖の最も外側の 412a60/409730 の 1 つ外側 frame) と
//         base 側 oob の最上位 frame (wasm 名前表は m11_boot.cjs.wasm の export section を直接パース)
import fs from 'fs';
const W = new URL('../work/m11_boot.cjs.wasm', import.meta.url).pathname;
const b = fs.readFileSync(W);
let pos = 8;
const leb = () => { let r = 0, s = 0, x; do { x = b[pos++]; r |= (x & 0x7f) << s; s += 7; } while (x & 0x80); return r >>> 0; };
const names = new Map();
while (pos < b.length) {
  const id = b[pos++]; const sz = leb(); const end = pos + sz;
  if (id === 7) { const n = leb(); for (let k = 0; k < n; k++) { const l = leb(); const nm = b.toString('utf8', pos, pos + l); pos += l; const kind = b[pos++]; const idx = leb(); if (kind === 0 && !names.has(idx)) names.set(idx, nm); } }
  pos = end;
}
const nameOf = (f) => { const m = /wasm-function\[(\d+)\]/.exec(f); return m ? (names.get(+m[1]) || '?') : f; };
const A = JSON.parse(fs.readFileSync(process.argv[2])), B = JSON.parse(fs.readFileSync(process.argv[3]));
const tally = (arr) => arr.reduce((o, r) => (o[r.kind] = (o[r.kind] || 0) + 1, o), {});
const trap = (o) => (o.oob || 0) + (o.halt0 || 0) + (o.abort || 0) + (o.other || 0);
const ta = tally(A), tb = tally(B);
console.log('base', JSON.stringify(ta), 'trap=' + trap(ta));
console.log('new ', JSON.stringify(tb), 'trap=' + trap(tb));
const tr = {}; const reg = [];
for (let i = 0; i < A.length; i++) { const k = A[i].kind + '->' + B[i].kind; tr[k] = (tr[k] || 0) + 1; if (A[i].kind === 'ok' && B[i].kind !== 'ok') reg.push(A[i].unit); }
console.log('transitions', JSON.stringify(tr));
console.log('ok->non-ok', reg.length, JSON.stringify(reg));
const callers = {};
for (const r of B) {
  if (r.kind !== 'halt0') continue;
  const fr = r.frames.map(nameOf);
  let last = -1; fr.forEach((f, i) => { if (f === 'function_412a60' || f === 'function_409730') last = i; });
  const c = last >= 0 && last + 1 < fr.length ? fr[last + 1].replace('function_', '') : '?';
  (callers[c] = callers[c] || []).push(r.unit);
}
console.log('new halt0 Error() caller:'); for (const [k, v] of Object.entries(callers).sort((x, y) => y[1].length - x[1].length)) console.log(' ', v.length, k, JSON.stringify(v));
const bt = {};
for (const r of A) { if (r.kind !== 'oob') continue; const f = nameOf(r.frames[0]).replace('function_', ''); (bt[f] = bt[f] || []).push(r.unit); }
console.log('base oob top frame:'); for (const [k, v] of Object.entries(bt).sort((x, y) => y[1].length - x[1].length)) console.log(' ', v.length, k, JSON.stringify(v));
