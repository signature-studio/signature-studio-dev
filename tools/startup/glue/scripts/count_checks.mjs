#!/usr/bin/env node
// count_checks.mjs — CAB-101 の REPORT 見出し数値を 1 コマンドで再計算する (規則 37)。
//   node tools/startup/glue/scripts/count_checks.mjs
//
// 数え方の定義 (規則 36):
//  - "C 単体チェック N" = wasm 化した C テスト (test/glue_unit.c) の stdout で
//      (a) `  ok   ` / `  FAIL ` で始まる行
//      (b) 段階 10 個の done 表示行 (`       stage <name> done=1`)
//    の総数 (1 行 = 1 チェック)。GLUE サマリ行 `pass=X fail=Y` と不一致なら警告する。
//  - "TS 単体チェック N" = test/glue_unit.ts の実行結果 `(pass=X fail=Y)`。
//  - "e2e 検証項目 N" = host/glue_e2e.ts の ok() 呼出し行数の静的カウント (別アルゴリズム)。
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const GLUE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const countLines = (text, re) => (text.match(re) ?? []).length;
const run = (args, cwd) => execFileSync(process.execPath, args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });

// --- 1. C 単体 (ST/MT): 実行して集計 ---
const cRes = {};
for (const mode of ['st', 'mt']) {
  const out = run([`work/unit_${mode}.cjs`], GLUE);
  const m = /GLUE (ALL PASS|FAIL) \(pass=(\d+) fail=(\d+)\)/.exec(out);
  cRes[mode] = {
    verdict: m?.[1], pass: Number(m?.[2] ?? 0), fail: Number(m?.[3] ?? 0),
    okLines: countLines(out, /^ {2}ok /gm) + countLines(out, /^ {7}stage /gm),
  };
}

// --- 2. TS 単体: 実行して集計 ---
const tsOut = run(['test/glue_unit.ts'], GLUE);
const tsM = /\(pass=(\d+) fail=(\d+)\)/.exec(tsOut);
const tsRes = { pass: Number(tsM?.[1] ?? 0), fail: Number(tsM?.[2] ?? 0), okLines: countLines(tsOut, /^ {2}ok /gm) };

// --- 3. 静的カウント (別アルゴリズム: ソースの ok( 呼出し数) ---
const countOkCalls = (file) => countLines(fs.readFileSync(path.join(GLUE, file), 'utf8'), /\bok\(/g);
const staticTs = countOkCalls('test/glue_unit.ts');
const staticE2e = countOkCalls('host/glue_e2e.ts');

console.log('C unit ST :', JSON.stringify(cRes.st));
console.log('C unit MT :', JSON.stringify(cRes.mt));
console.log('TS unit   :', JSON.stringify(tsRes), ' static ok( calls =', staticTs);
console.log('e2e static ok( calls =', staticE2e);
console.log(`SUMMARY: C(unit)=${cRes.st.pass}/${cRes.mt.pass} checks TS(unit)=${tsRes.pass} checks e2e(static)=${staticE2e}`);
const allZero = [cRes.st, cRes.mt, tsRes].every((r) => r.fail === 0);
for (const [k, r] of Object.entries(cRes)) {
  if (r.pass + r.fail !== r.okLines) console.log(`WARN: C ${k}: summary ${r.pass}+${r.fail} != ok lines ${r.okLines}`);
}
if (tsRes.pass + tsRes.fail !== tsRes.okLines) console.log(`WARN: TS: summary != ok lines ${tsRes.okLines}`);
console.log(allZero ? 'count_checks: all zero fail' : 'count_checks: NON-ZERO FAIL');
