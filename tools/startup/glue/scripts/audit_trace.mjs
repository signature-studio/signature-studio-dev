#!/usr/bin/env node
// audit_trace.mjs — 別アルゴリズムによる検算 (規則 37: 同じ実装の再実行は独立再計算ではない)。
//   node tools/startup/glue/scripts/audit_trace.mjs [--dir <workDir>]
//
// count_checks.mjs は「テストが自己報告した成功数」を数える。本スクリプトは別系統で
// **glue が吐いた trace テキストそのもの**を読み、以下を独立に検算する:
//   A. stage= の enter 順が規約順 (paths>...>shutdown) と一致するか
//   B. `C:\Users\user` という文字列が trace に 0 件か (username=webstudio の残存)
//   C. 写像結果に `/c/Users/` 残差が 0 件か (既定表に乗らなかった Win パス)
//   D. stage= の ok 行が 10 段階すべて揃っているか
// 判定はグルーの検査 API (glue_order_violations / pathreg_mount_count 等) を**使わず**、
// trace 文字列の行分割と完全一致比較のみで行う (= count_checks.mjs とは別アルゴリズム)。
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const GLUE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ARGS = process.argv.slice(2);
const WORK = ARGS.includes('--dir') ? ARGS[ARGS.indexOf('--dir') + 1] : path.join(GLUEDir(), 'work/audit2');
function GLUEDir() { return GLUE; }

const CANON = ['paths', 'registry', 'pump', 'vfs', 'pre_dllmain', 'dllmain', 'host', 'boot', 'post', 'shutdown'];

fs.mkdirSync(WORK, { recursive: true });
const traceLines = collectTrace();

const enters = traceLines.filter((l) => /stage=\S+ enter/.test(l)).map((l) => l.match(/stage=(\S+) enter/)[1]);
const oks = traceLines.filter((l) => /stage=\S+ ok \(/.test(l)).map((l) => l.match(/stage=(\S+) ok/)[1]);
const nUser = traceLines.filter((l) => l.includes('C:\\Users\\user')).length;
const nResid = traceLines.filter((l) => /-> 0 \/c\/Users\//.test(l)).length;
const mapped = traceLines.filter((l) => /^map /.test(l)).length;
const a = JSON.stringify(enters) === JSON.stringify(CANON);
const b = nUser === 0;
const c = nResid === 0;
const d = JSON.stringify(oks) === JSON.stringify(CANON);

console.log(`A enter order    = ${enters.join('>')} -> ${a ? 'MATCH' : 'MISMATCH'}`);
console.log(`B C:\\Users\\user  = ${nUser}件 -> ${b ? '0 (PASS)' : 'NONZERO (FAIL)'}`);
console.log(`C /c/Users/ 残差  = ${nResid}件 -> ${c ? '0 (PASS)' : 'NONZERO (FAIL)'}`);
console.log(`D stage ok 列     = ${oks.join('>')} -> ${d ? 'ALL 10' : 'INCOMPLETE'}`);
console.log(`  (写像行数=${mapped} / trace 行数=${traceLines.length})`);
const pass = a && b && c && d;
console.log(pass ? 'audit_trace: PASS' : 'audit_trace: FAIL');
process.exit(pass ? 0 : 1);

/** glue_host を起動して trace を採取する (判定はしない) */
function collectTrace() {
  const script = `
    const { GlueHost } = await import(${JSON.stringify(path.join(GLUEDir(), 'host/glue_host.ts'))});
    const mod = await import(${JSON.stringify(path.join(GLUEDir(), 'work/glue_mod.mjs'))});
    const m = await mod.default();
    const h = new GlueHost(m, { username: 'webstudio', workDir: ${JSON.stringify(WORK)} });
    await h.runAll('?open=Demo.flp');
    console.log('TRACEJSON' + JSON.stringify(h.trace()));
  `;
  const r = execFileSync(process.execPath, ['-e', script], { cwd: GLUEDir(), encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  const line = r.trim().split('\n').find((l) => l.startsWith('TRACEJSON'));
  return JSON.parse(line.slice('TRACEJSON'.length));
}
