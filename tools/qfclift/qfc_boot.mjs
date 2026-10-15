#!/usr/bin/env node
// qfc_boot.mjs — QuickFontCache_x64.dll の boot 実行 (T-SH-60 / #3289)。qfc_boot.sh が呼ぶ。
//   env: QFC_CJS (x64c lift した qfcl.cjs の絶対パス) / QFC_OUT (結果 JSON の出力先)
// 手順: fle_data_install → fle_init → DllMain(hinst, DLL_PROCESS_ATTACH, 0) → FontCache_GetStats(buf) → FontCache_CleanUp
// 1 段でも trap / 非 ok なら以降は実行しない (abort 後の wasm 状態は使えない)。fprintf(stderr) は printErr で捕まえる。
// PASS = 全段 ok かつ DllMain の戻り値 (RAX) が 1。exit code: PASS 0 / FAIL 1。
import { writeFileSync } from 'node:fs';

const IMG = 0x400000;                        // ImageBase (guest VA = wasm 線形アドレス)
const DLLMAIN = 0x59c1f0;                    // AddressOfEntryPoint (RVA 0x19c1f0) + ImageBase
const GETSTATS = 0x57faf0;                   // export FontCache_GetStats
const CLEANUP = 0x57f980;                    // export FontCache_CleanUp

const errs = [];
const mod = await import(process.env.QFC_CJS);
const m = await mod.default({ printErr: (s) => errs.push(String(s)), print: () => {} });
m._fle_data_install();
m._fle_init();

const steps = [];
function step(name, va, args) {
  const rec = { name, va: '0x' + va.toString(16), status: 'ok', rax: null, trap: '', stderr: [] };
  errs.length = 0;
  const t0 = performance.now();
  try {
    const g = [...args, 0, 0, 0, 0].slice(0, 4).map(BigInt);
    rec.rax = '0x' + BigInt.asUintN(64, BigInt(m._fle_run(va, g[0], g[1], g[2], g[3], 0n, 0n, 0n, 0n))).toString(16);
  } catch (e) {
    rec.status = 'trap';
    rec.trap = String(e).slice(0, 160);
  }
  rec.ms = Math.round(performance.now() - t0);
  rec.soft = errs.filter((s) => s.startsWith('[qfc-soft] ')).map((s) => s.slice(11));
  rec.stderr = errs.filter((s) => s.includes('[fle]')).slice(-4);
  steps.push(rec);
  return rec.status === 'ok';
}

const buf = m._malloc(0x1000);
let ok = step('DllMain(PROCESS_ATTACH)', DLLMAIN, [IMG, 1, 0]);
if (ok) ok = step('FontCache_GetStats', GETSTATS, [buf]);
if (ok) ok = step('FontCache_CleanUp', CLEANUP, []);

// soft stub (呼出しを記録して 0 を返す) に当たった段は、実物の import で動いたことの証拠にならない。
// 全段 ok かつ DllMain が 1 を返し、soft stub の呼出しが 0 件のときだけ PASS。soft が 1 件以上なら SOFT (exit 1)。
const dll = steps[0];
const softN = steps.reduce((n, s) => n + s.soft.length, 0);
const allOk = steps.length === 3 && steps.every((s) => s.status === 'ok') && dll.rax === '0x1';
const verdict = !allOk ? 'FAIL' : softN === 0 ? 'PASS' : 'SOFT';
const stop = steps.find((s) => s.status !== 'ok');
const out = {
  verdict, soft_calls: softN, steps,
  soft_names: [...new Set(steps.flatMap((s) => s.soft))],
  stopped_at: stop ? stop.name : null, stopped_by: stop ? (stop.stderr[0] || stop.trap) : null,
};
writeFileSync(process.env.QFC_OUT, JSON.stringify(out, null, 2));
console.log('[qfc_boot] verdict', verdict, '| soft calls', softN, '| steps', steps.map((s) => `${s.name}=${s.status}${s.rax ? ' rax=' + s.rax : ''}`).join(' ; '));
if (stop) console.log('[qfc_boot] stopped at', stop.name, '|', out.stopped_by);
process.exitCode = verdict === 'PASS' ? 0 : 1;
