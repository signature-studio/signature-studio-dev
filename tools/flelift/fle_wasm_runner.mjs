#!/usr/bin/env node
// fle_wasm_runner.mjs — fle_diff.py の wasm 側ランナ: FLE_CASES (env JSON) の各 case を実行し
// work/wasm_results.json に書く。
// 比較領域: image (.data/.bss 0xfa5000..0x156f000) / TEB 0x1D00000..+0x400 / scratch 0x20000000..+0x100000 /
//           arena 0x2100000..0x3100000 (VirtualAlloc bump)。差分は 8B block で列挙。
import { writeFileSync } from 'node:fs';

const cases = JSON.parse(process.env.FLE_CASES);
const mod = await import(process.env.FLE_CJS);
const m = await mod.default();
m._fle_data_install();
m._fle_init();
const U8 = m.HEAPU8;
const dv = new DataView(U8.buffer);

const REGIONS = [
  ['image', 0x13a5000, 0x196f000],   // .data (VA 0x13a5000..0x15e5008) + .bss (VA 0x15e6000..0x196ee9c)
  ['teb', 0x1D00000, 0x1D00400],
  ['scratch', 0x20000000, 0x20000000 + 0x100000],
  ['arena', 0x2100000, 0x3100000],
];
// BigUint64Array view (8B 整列 region)
const views = REGIONS.map(([nm, lo, hi]) => [nm, lo, new BigUint64Array(U8.buffer, lo, (hi - lo) / 8)]);

function diffBlocks(base) {
  const out = [];
  for (const [nm, lo, cur] of views) {
    const pri = base.get(nm);
    for (let k = 0; k < cur.length; k++) {
      if (cur[k] !== pri[k]) out.push({ r: nm, o: '0x' + (k * 8).toString(16), b: '0x' + pri[k].toString(16), a: '0x' + cur[k].toString(16) });
    }
  }
  return out;
}

function snapshot() {
  const pri = new Map();
  for (const [nm, lo, cur] of views) pri.set(nm, cur.slice());
  return pri;
}

function prepUstrasg(selfAssign) {
  const slot = 0x20000000, st = 0x20001000 + 12;
  dv.setBigUint64(slot, selfAssign ? BigInt(st) : 0n, true);
  dv.setInt16(st - 12, 1200, true);      // codepage
  dv.setInt16(st - 10, 2, true);         // elemsize
  dv.setInt32(st - 8, 1, true);          // refcnt
  dv.setInt32(st - 4, 8, true);          // len
  for (let i = 0; i < 16; i++) U8[st + i] = 0x41 + i;
}

function prepCase(c) {
  if (c.prep === 'ustrasg') prepUstrasg(0);
  else if (c.prep === 'ustrasg_self') prepUstrasg(1);
  else if (c.prep === 'pat') for (let a = 0x20004000; a < 0x20006000; a++) U8[a] = ((a - 0x20004000) * 13 + 7) & 0xff;
}

function resetState() {
  // CPU 状態 full reset (fle_reset) + .bss (VA 0x15e5008..0x196f000) + scratch + arena を 0 に
  // (native driver の fle_reset+zero と同一条件) → TEB/alloc log 再初期化
  U8.fill(0, 0x15e5008, 0x196f000);
  U8.fill(0, 0x20000000, 0x3100000);
  m._fle_reset();
  m._fle_init();
}

const results = [];
for (const c of cases) {
  resetState();
  prepCase(c);
  const pri = snapshot();
  let status = 'ok', rax = null, x0 = null, trap = '';
  try {
    (c.stk || []).forEach((v, i) => m._fle_set_stackarg(i, BigInt(v)));
    rax = '0x' + BigInt.asUintN(64, BigInt(m._fle_run(c.fn, ...c.gpr.map(BigInt), ...c.xmm.map(BigInt),
      ...Array(4 - c.gpr.length).fill(0n), ...Array(4 - c.xmm.length).fill(0n)))).toString(16);
    x0 = '0x' + BigInt.asUintN(64, BigInt(m._fle_xmm0())).toString(16);
  } catch (e) { status = 'trap'; trap = String(e).slice(0, 120); }
  results.push({ fn: c.fn, name: c.name, id: c.id, desc: c.desc, status, rax, x0,
                 mem: status === 'ok' ? diffBlocks(pri) : [], trap });
}
writeFileSync(new URL('./work/wasm_results.json', import.meta.url).pathname,
  JSON.stringify({ cases: results }));
console.log('[fle_wasm_runner] cases', results.length, 'ok', results.filter(r => r.status === 'ok').length);
