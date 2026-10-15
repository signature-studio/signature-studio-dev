#!/usr/bin/env node
// qfc_direct.mjs — FontCache_GetStats / FontCache_CleanUp を DllMain を経由せず直接呼ぶ (T-SH-113 / #4296)。
//   env: QFC_CJS (x64c lift した qfcl.cjs の絶対パス) / QFC_OUT (結果 JSON の出力先)
// 手順: fle_data_install → fle_init → FontCache_GetStats(buf) → FontCache_CleanUp(a, b)。
// DllMain (PROCESS_ATTACH) は実行しない (qfc_boot.mjs の boot 経路は LocalAlloc / ExitProcess で止まるため)。
// 引数: GetStats は rcx=buf (逆アセンブル: buf に 0x50 byte を書き、+4/+8/+0xc に dword)。
//       CleanUp は ecx/edx の 2 つの int (逆アセンブル: 境界比較あり)。仕様書は無いので、この値は推定呼出し。
// 判定は「停止点と rax」の記録のみ。PASS/FAIL の意味付けはしない。
import { writeFileSync } from 'node:fs';

const GETSTATS = 0x57faf0;
const CLEANUP = 0x57f980;

const errs = [];
const mod = await import(process.env.QFC_CJS);
const m = await mod.default({ printErr: (s) => errs.push(String(s)), print: () => {} });
m._fle_data_install();
m._fle_init();

const steps = [];
function step(name, va, args) {
  const rec = { name, va: '0x' + va.toString(16), args: args.map(String), status: 'ok', rax: null, trap: '', soft: [], stderr: [] };
  errs.length = 0;
  try {
    const g = [...args, 0, 0, 0, 0].slice(0, 4).map(BigInt);
    rec.rax = '0x' + BigInt.asUintN(64, BigInt(m._fle_run(va, g[0], g[1], g[2], g[3], 0n, 0n, 0n, 0n))).toString(16);
  } catch (e) {
    rec.status = 'trap';
    rec.trap = String(e).slice(0, 160);
  }
  rec.soft = errs.filter((s) => s.startsWith('[qfc-soft] ')).map((s) => s.slice(11));
  rec.stderr = errs.filter((s) => s.includes('[fle]')).slice(-4);
  steps.push(rec);
  return rec.status === 'ok';
}

const buf = m._malloc(0x1000);
step('FontCache_GetStats', GETSTATS, [buf]);
// CleanUp は GetStats が trap しても独立に呼ぶ (wasm の状態は trap 後に信用できないため、別 instance で実行する)。
const cu = await mod.default({ printErr: (s) => errs.push(String(s)), print: () => {} });
cu._fle_data_install();
cu._fle_init();
const cuSteps = [];
errs.length = 0;
try {
  const r = BigInt.asUintN(64, BigInt(cu._fle_run(CLEANUP, 0n, 0n, 0n, 0n, 0n, 0n, 0n, 0n)));
  cuSteps.push({ name: 'FontCache_CleanUp', va: '0x' + CLEANUP.toString(16), args: ['0', '0'], status: 'ok', rax: '0x' + r.toString(16), trap: '', soft: [], stderr: errs.filter((s) => s.includes('[fle]')).slice(-4) });
} catch (e) {
  cuSteps.push({ name: 'FontCache_CleanUp', va: '0x' + CLEANUP.toString(16), args: ['0', '0'], status: 'trap', rax: null, trap: String(e).slice(0, 160), soft: [], stderr: errs.filter((s) => s.includes('[fle]')).slice(-4) });
}
steps.push(...cuSteps);

const out = { steps, stopped_at: steps.find((s) => s.status !== 'ok')?.name ?? null };
writeFileSync(process.env.QFC_OUT, JSON.stringify(out, null, 2));
for (const s of steps) console.log('[qfc_direct]', s.name, s.status, s.rax ?? '', 'soft', s.soft.length, '|', s.trap || s.stderr.at(-1) || '');
