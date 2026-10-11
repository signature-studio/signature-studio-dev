// accept_recount.mjs — CAB-168 / CAB-271 検収: pathreg REPORT の見出し数値を別アルゴリズムで再計算する
// (規則 37)。検収 agent が新規に書いた独立再計算。実装側の e2e.mjs とは別系統:
//   - e2e.mjs は C↔JS 写像一致そのものを assert する
//   - 本スクリプトは「REPORT が主張している数」を、ソース/出力のテキスト解析・別経路
//     (defaultMounts() / build 済み module の生 export / C 単体 binary の**再実行**) から数え直す
// 実行: bash tools/shimx/pathreg/scripts/build.sh test && node tools/shimx/pathreg/scripts/accept_recount.mjs
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const R = (p) => readFileSync(path.join(ROOT, p), 'utf8');
let bad = 0;
const chk = (label, got, want) => {
  const ok = got === want;
  if (!ok) bad++;
  console.log(`${label}=${got} (REPORT: ${want}) -> ${ok ? 'MATCH' : 'MISMATCH'}`);
};

// --- 1. 既定マウント表の件数 (JS 側 / C 側) ---
const { defaultMounts } = await import(path.join(ROOT, 'js/pathmap.mjs'));
const dm = defaultMounts();
const createB = (await import(path.join(ROOT, 'build/module_b.mjs'))).default;
const mod = await createB();
mod._shimx_init();
mod._pathreg_install();
const cCount = mod._pathreg_mount_count();
console.log(`mount table: JS defaultMounts()=${dm.length}  C pathreg_mount_count()=${cCount}  -> ${dm.length === cCount && cCount === 8 ? 'MATCH(8)' : 'MISMATCH'}`);
if (dm.length !== 8 || cCount !== 8) bad++;
for (const m of dm) console.log(`    ${m.win}  ->  ${m.target}  (flags=${m.flags})`);

// --- 2. e2e の fixture 件数 + 各 fixture の C/JS 写映射 (不変確認のため全件印字) ---
const e2eSrc = R('test/e2e.mjs');
const fxBlock = /const fixtures = \[([\s\S]*?)\n  \];/.exec(e2eSrc)[1];
const fixtures = (fxBlock.match(/^\s*'/gm) || []).length;
console.log(`C<->JS fixtures: e2e.mjs array entries=${fixtures}  (REPORT claims 16) -> ${fixtures === 16 ? 'ACTUAL=16' : `ACTUAL=${fixtures}`}`);
if (fixtures !== 16) bad++;

// --- 3. C 単体の各件数 (関数名で囲んだ cases[] と CHECK( を数える: 数え方は REPORT §8-1) ---
const tp = R('test/test_pathreg.c');
const td = R('test/test_defaults.c');
const fnBody = (src, name) => {
  const m = new RegExp(`(?:static void|int) ${name}\\(void\\) \\{[\\s\\S]*?\\n\\}`).exec(src);
  return m ? m[0] : '';
};
/* 定義: 「N 例」= 各 test 関数の cases[] 初期化子の要素数 ({} で始まる行を数える)。「CHECK( 総数」= 関数本文の
   CHECK( 出現数 (test_common.h のマクロ呼出し。同じ行に 2 個ある場合は 2 と数える) */
const casesOf = (body) => {
  const m = /cases\[\] = \{([\s\S]*?)\n    \};/.exec(body);
  return m ? (m[1].match(/^\s*\{/gm) || []).length : 0;
};
const normCases = casesOf(fnBody(tp, 'test_normalize'));
const mapCases = casesOf(fnBody(tp, 'test_map'));
const defCases = casesOf(fnBody(td, 'main'));
const normExtra = (fnBody(tp, 'test_normalize').match(/CHECK\(pathreg_normalize\(/g) || []).length;
chk('normalize cases', normCases, 18);
chk('extra CHECK pathreg_normalize', normExtra, 4);
chk('test_map cases', mapCases, 8);
chk('test_defaults map cases', defCases, 9);
console.log(`C unit CHECK( 総数: test_pathreg.c=${(tp.match(/CHECK\(/g) || []).length} / test_defaults.c=${(td.match(/CHECK\(/g) || []).length}`);

// --- 4. CAB-271: set_paths の明示設定が既定ロードに負けないこと (静的解析 + binary 再実行) ---
// 実行は build.sh test の成果物を使う (未 build なら本節は FAIL として report する)
const run = (f) => {
  try { return String(execFileSync(process.execPath, [f], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })); }
  catch (e) { return `__FAIL__ ${String(e.stderr || e.message).trim()}`; }
};
const tpOut = run(path.join(ROOT, 'build/test_pathreg_st.cjs'));
const tdOut = run(path.join(ROOT, 'build/test_defaults_st.cjs'));
const cabOk = tpOut.includes('OK pathreg: defaults vs explicit set_paths (CAB-271)');
const cabFail = /FAIL .*test_defaults_vs_explicit|__FAIL__/.test(tpOut);
console.log(`CAB-271 explicit-paths (test_pathreg_st 再実行): -> ${cabOk && !cabFail ? 'PASS' : 'FAIL'}`);
if (!(cabOk && !cabFail)) bad++;
console.log(`CAB-271 default-path   (test_defaults_st 再実行): -> ${tdOut.includes('PATHREG DEFAULTS ALL PASS') ? 'PASS' : 'FAIL: ' + tdOut.split('\n').slice(0, 3).join(' ')}`);
if (!tdOut.includes('PATHREG DEFAULTS ALL PASS')) bad++;
// 明示設定経路がalpha表を使うこと (既定 webstudio を使わない) を static に確認
const cabBlock = /static void test_defaults_vs_explicit\(void\) \{[\s\S]*?\n\}/.exec(tp);
const cabChecks = cabBlock ? (cabBlock[0].match(/CHECK\(/g) || []).length : 0;
const hasWebstudioGuard = cabBlock ? cabBlock[0].includes('nWebstudio == 0') : false;
console.log(`CAB-271 test body: CHECK(=${cabChecks} / webstudio 残存 0 のガード=${hasWebstudioGuard}`);
if (cabChecks < 10 || !hasWebstudioGuard) bad++;

// --- 5. 行数 (wc -l 相当: 改行数) ---
const files = ['include/pathreg.h', 'src/pathmap.c', 'src/regpersist.c', 'src/pathreg_internal.h',
  'js/pathmap.mjs', 'js/regbridge.mjs', 'test/test_pathreg.c', 'test/test_defaults.c',
  'test/pathmap.test.mjs', 'test/e2e.mjs', 'scripts/build.sh', 'scripts/e2e.sh'];
const loc = {};
for (const f of files) loc[f] = R(f).split('\n').length - (R(f).endsWith('\n') ? 1 : 0);
const sum = (fs) => fs.reduce((a, f) => a + loc[f], 0);
const C = sum(['include/pathreg.h', 'src/pathmap.c', 'src/regpersist.c', 'src/pathreg_internal.h']);
const JS = sum(['js/pathmap.mjs', 'js/regbridge.mjs']);
const TEST = sum(['test/test_pathreg.c', 'test/test_defaults.c', 'test/pathmap.test.mjs', 'test/e2e.mjs']);
const SCRIPT = sum(['scripts/build.sh', 'scripts/e2e.sh']);
console.log(`LOC: C=${C} JS=${JS} TEST=${TEST} SCRIPT=${SCRIPT} TOTAL=${C + JS + TEST + SCRIPT}`);
for (const f of files) console.log(`    ${f} = ${loc[f]}`);
chk('LOC C', C, 474); chk('LOC JS', JS, 461); chk('LOC TEST', TEST, 654); chk('LOC SCRIPT', SCRIPT, 117);

console.log(bad === 0 ? 'accept_recount: MATCH (mounts 8 / fixtures 16 / CAB-271 PASS / LOC 1706)'
                      : `accept_recount: MISMATCH (${bad} 件)`);
process.exit(bad === 0 ? 0 : 1);
