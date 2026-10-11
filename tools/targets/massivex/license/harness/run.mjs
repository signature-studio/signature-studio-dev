// MX-2 harness runner (node) — SR-2b harness パターン
// emcc -sMODULARIZE の直接 export (_mx_*) を呼ぶ (i64 戻りは BigInt)。
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [modPath, reportFlag, reportPath] = process.argv.slice(2);
if (!modPath) {
  console.error('usage: node run.mjs <h.cjs> [--report out.json]');
  process.exit(2);
}
const mod = await import(pathToFileURL(resolve(modPath)).href);
const factory = mod.default ?? mod;
const inst = await factory();

const names = {
  1: 'T1 checkSerial_pre   serial不一致→matched=0 (demo 対比)',
  2: 'T2 checkSerial_patch serial不一致→matched=1, rc=0',
  3: 'T3 checkSerial_pre   serial一致→matched=1 (sanity)',
  4: 'T4 getSub_pre        subscription無→rc=18 (demo 対比)',
  5: 'T5 getSub_patch      subscription無→rc=0',
  6: 'T6 getSub_patch      subscription有→rc=0 (型copyはL-MX1)',
  7: 'T7 evalRAS2_pre      SysID/AuthKey未設定→state!=3',
  8: 'T8 evalRAS2_patch    同左でも state==3 (N1a)',
  9: 'T9 evalRAS2_pre      全判定NG→state!=3 (demo 対比)',
  10: 'T10 evalRAS2_patch   同左でも state==3 (N1b+N1c)',
  11: 'T11 evalRAS2_patch   本来activated判定→state==3',
};

const norm = (v) => (typeof v === 'bigint' ? Number(v) : Number(v));

let pass = 0;
const rows = [];
let all = 1;
for (let i = 1; i <= 11; i++) {
  let ok, det;
  try {
    ok = norm(inst._mx_run_one(BigInt(i))) === 1;
    det = norm(inst['_mx_get_detail_' + i]());
  } catch (e) {
    ok = false;
    det = 'TRAP: ' + String(e.message).slice(0, 90);
  }
  if (ok) pass++; else all = 0;
  rows.push({ id: `T${i}`, name: names[i], ok, detail: det });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${names[i]}  (detail=${det})`);
}
console.log(`\nmx harness: ${pass}/11 PASS (all=${all})`);
if (reportFlag === '--report') {
  await writeFile(reportPath, JSON.stringify({ pass, total: 11, all: all === 1, rows }, null, 1));
  console.log('report ->', reportPath);
}
process.exit(all === 1 ? 0 : 1);
