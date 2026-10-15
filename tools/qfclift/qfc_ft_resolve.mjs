#!/usr/bin/env node
// qfc_ft_resolve.mjs — FT 解決 (0x563000) を直接呼んで、FontCache_GetStats が読む関数ポインタ [0x5d8b48] が埋まるかを測る (T-SH-113 / #4296)。
//   env: QFC_CJS (x64c lift した qfcl.cjs の絶対パス) / QFC_OUT (結果 JSON の出力先)
// 手順: fle_data_install → fle_init → 各アドレスを読む (before) → FT 解決 0x563000 を直接呼ぶ → 再読 (after) → GetStats を呼ぶ。
// 読み出しは guest VA = wasm アドレス (恒等写像, fle_cpu.h の A_) で HEAPU8 を読む。判定は値の記録のみ。
import { writeFileSync } from 'node:fs';

const FT_RESOLVE = 0x563000;
const GETSTATS = 0x57faf0;
const WATCH = { ptr_5d8b48: 0x5d8b48, ptr_5cae18: 0x5cae18, cnt_5d9f20: 0x5d9f20 };

const errs = [];
const mod = await import(process.env.QFC_CJS);
const m = await mod.default({ printErr: (s) => errs.push(String(s)), print: () => {} });
m._fle_data_install();
m._fle_init();

const rd64 = (va) => {
  const b = m.HEAPU8;
  let v = 0n;
  for (let i = 7; i >= 0; i--) v = (v << 8n) | BigInt(b[va + i]);
  return '0x' + v.toString(16);
};
const snap = () => Object.fromEntries(Object.entries(WATCH).map(([k, va]) => [k, rd64(va)]));

const rec = { before: snap(), resolve: null, after: null, getstats: null };

errs.length = 0;
try {
  const r = BigInt.asUintN(64, BigInt(m._fle_run(FT_RESOLVE, 0n, 0n, 0n, 0n, 0n, 0n, 0n, 0n)));
  rec.resolve = { status: 'ok', rax: '0x' + r.toString(16), stderr: errs.filter((s) => s.includes('[fle]')).slice(-4) };
} catch (e) {
  rec.resolve = { status: 'trap', trap: String(e).slice(0, 160), stderr: errs.filter((s) => s.includes('[fle]')).slice(-4) };
}
rec.after = snap();

const buf = m._malloc(0x1000);
errs.length = 0;
try {
  const r = BigInt.asUintN(64, BigInt(m._fle_run(GETSTATS, BigInt(buf), 0n, 0n, 0n, 0n, 0n, 0n, 0n)));
  rec.getstats = { status: 'ok', rax: '0x' + r.toString(16), stderr: errs.filter((s) => s.includes('[fle]')).slice(-4) };
} catch (e) {
  rec.getstats = { status: 'trap', trap: String(e).slice(0, 160), stderr: errs.filter((s) => s.includes('[fle]')).slice(-4) };
}

writeFileSync(process.env.QFC_OUT, JSON.stringify(rec, null, 2));
console.log('[qfc_ft] before', JSON.stringify(rec.before));
console.log('[qfc_ft] resolve', rec.resolve.status, rec.resolve.rax ?? rec.resolve.trap);
console.log('[qfc_ft] after ', JSON.stringify(rec.after));
console.log('[qfc_ft] getstats', rec.getstats.status, rec.getstats.rax ?? rec.getstats.trap, '|', rec.getstats.stderr.at(-1) ?? '');
