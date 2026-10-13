#!/usr/bin/env node
// qfc_wasm_runner.mjs — qfc_diff.py の wasm 側。QFC_CASES (JSON) を実行し QFC_OUT に結果 JSON を書く。
// case: {id, fn, gpr[4], stk[], writes:[{va, hex}], cmp:[{va, len}]} (native 側 qfc_natdrv と同一入力)
import { readFileSync, writeFileSync } from 'node:fs';

const cases = JSON.parse(readFileSync(process.env.QFC_CASES, 'utf8'));
const mod = await import(process.env.QFC_CJS);
const m = await mod.default();
m._fle_data_install();
m._fle_init();
const U8 = m.HEAPU8;
const hex = (a, n) => Buffer.from(U8.buffer, a, n).toString('hex');

const results = [];
for (const c of cases) {
  U8.fill(0, 0x20000000, 0x20100000);
  m._fle_reset();
  m._fle_init();
  for (const w of c.writes) Buffer.from(w.hex, 'hex').copy(U8, parseInt(w.va, 16));
  let status = 'ok', rax = null, x0 = null, trap = '';
  try {
    c.stk.forEach((v, i) => m._fle_set_stackarg(i, BigInt(v)));
    const g = c.gpr.map(BigInt);
    rax = '0x' + BigInt.asUintN(64, BigInt(m._fle_run(c.fn, g[0], g[1], g[2], g[3], 0n, 0n, 0n, 0n))).toString(16);
    x0 = '0x' + BigInt.asUintN(64, BigInt(m._fle_xmm0())).toString(16);
  } catch (e) { status = 'trap'; trap = String(e).slice(0, 160); }
  results.push({ id: c.id, status, rax, x0, trap, mem: c.cmp.map((r) => hex(parseInt(r.va, 16), r.len)) });
}
writeFileSync(process.env.QFC_OUT, JSON.stringify(results));
console.log('[qfc_wasm_runner] cases', results.length, 'ok', results.filter((r) => r.status === 'ok').length);
