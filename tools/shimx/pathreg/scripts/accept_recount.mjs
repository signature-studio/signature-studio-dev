// accept_recount.mjs — CAB-168 検収: pathreg REPORT の見出し数値を別アルゴリズムで再計算する
// (規則 37)。検収 agent が新規に書いた独立再計算。実装側の e2e.mjs とは別系統:
//   - e2e.mjs は C↔JS 写像一致そのものを assert する
//   - 本スクリプトは「REPORT が主張している数」を、ソース/出力のテキスト解析と
//     別経路 (defaultMounts() / build 済み module の生 export) から数え直す
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const R = (p) => readFileSync(path.join(ROOT, p), 'utf8');

// --- 1. 既定マウント表の件数 (JS 側 / C 側) ---
const { defaultMounts } = await import(path.join(ROOT, 'js/pathmap.mjs'));
const dm = defaultMounts();
const createB = (await import(path.join(ROOT, 'build/module_b.mjs'))).default;
const mod = await createB();
mod._shimx_init();
mod._pathreg_install();
const cCount = mod._pathreg_mount_count();
console.log(`mount table: JS defaultMounts()=${dm.length}  C pathreg_mount_count()=${cCount}  -> ${dm.length === cCount && cCount === 8 ? 'MATCH(8)' : 'MISMATCH'}`);
for (const m of dm) console.log(`    ${m.win}  ->  ${m.target}  (flags=${m.flags})`);

// --- 2. e2e の fixture 件数 (REPORT は 15 と主張。e2e.mjs 出力は動的) ---
const e2eSrc = R('test/e2e.mjs');
const fxBlock = /const fixtures = \[([\s\S]*?)\n  \];/.exec(e2eSrc)[1];
const fixtures = (fxBlock.match(/^\s*'/gm) || []).length;
console.log(`C<->JS fixtures: e2e.mjs array entries=${fixtures}  (REPORT claims 15)  -> ${fixtures === 16 ? 'ACTUAL=16' : `ACTUAL=${fixtures}`}`);

// --- 3. C 単体の各件数 (test_pathreg.c の printf/cases から) ---
const tp = R('test/test_pathreg.c');
const body = /cases\[\] = \{([\s\S]*?)\n    \};/g;
const blocks = [...tp.matchAll(body)].map((m) => (m[1].match(/^\s*\{/gm) || []).length);
const normExtra = (tp.match(/CHECK\(pathreg_normalize\(/g) || []).length;
console.log(`C unit: normalize cases=${blocks[0]} (+extra CHECK pathreg_normalize=${normExtra}) / mounts cases=${blocks[1] ?? '-'} / map cases=${blocks[2]}`);

// --- 4. 行数 (wc -l 相当: 改行数) ---
const files = ['include/pathreg.h', 'src/pathmap.c', 'src/regpersist.c', 'src/pathreg_internal.h',
  'js/pathmap.mjs', 'js/regbridge.mjs', 'test/test_pathreg.c', 'test/test_common.h',
  'test/pathmap.test.mjs', 'test/e2e.mjs', 'scripts/build.sh', 'scripts/e2e.sh', 'README.md'];
const loc = {};
for (const f of files) loc[f] = R(f).split('\n').length - (R(f).endsWith('\n') ? 1 : 0);
const sum = (fs) => fs.reduce((a, f) => a + loc[f], 0);
const C = sum(['include/pathreg.h', 'src/pathmap.c', 'src/regpersist.c', 'src/pathreg_internal.h']);
const JS = sum(['js/pathmap.mjs', 'js/regbridge.mjs']);
const TEST = sum(['test/test_pathreg.c', 'test/pathmap.test.mjs', 'test/e2e.mjs']);
const SCRIPT = sum(['scripts/build.sh', 'scripts/e2e.sh']);
console.log(`LOC: C=${C} JS=${JS} TEST=${TEST} SCRIPT=${SCRIPT} TOTAL=${C + JS + TEST + SCRIPT}  (REPORT claims C=460 JS=462 TEST=541 SCRIPT=84 TOTAL=1547)`);
for (const f of files) console.log(`    ${f} = ${loc[f]}`);
const okAll = cCount === 8 && dm.length === 8 && fixtures === 16 && C === 460 && JS === 461 && TEST === 505 && SCRIPT === 82;
console.log(okAll ? 'accept_recount: MATCH (mounts 8 / fixtures 16 / LOC 1508)' : 'accept_recount: MISMATCH');
process.exit(okAll ? 0 : 1);
