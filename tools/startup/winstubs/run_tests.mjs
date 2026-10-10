#!/usr/bin/env node
// winstubs テストランナ (winstubs.sh から呼ぶ)。全チェックを実行し、失敗があれば exit 1。
//   units : data/retval_table.tsv の全行 × (ST, MT) 突合 + 終了フック (E01.01)
//   diff  : shimx 単体 (baseline) との差分表を実測生成 → data/diff_table.tsv。api_matrix.tsv の impl 宣言と整合検査
//   link  : リンクテスト (全 API がリンク可 / GetProcAddress 解決 / shimx 単体で未解決になる集合 == new 宣言集合)
//   boot  : 起動シーケンス e2e (data/boot_expect.tsv)。seed は data/vreg_seed.json から生成
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WORK = process.argv[2] || path.join(HERE, '..', 'work', 'winstubs');
const SEED = path.join(HERE, '..', 'data', 'vreg_seed.json');
const require = createRequire(import.meta.url);

let fails = 0, checks = 0;
const summary = {};
const ok = (cond, msg) => { checks++; if (!cond) { fails++; console.log(`  FAIL: ${msg}`); } return cond; };
const tsv = (f) => readFileSync(f, 'utf8').split('\n').filter((l) => l && !l.startsWith('#')).map((l) => l.split('\t'));

function run(bin, args = []) {
  const r = spawnSync(process.execPath, [bin, ...args], { encoding: 'utf8', timeout: 120000 });
  return r;
}
function parseKV(out) {
  const m = new Map();
  for (const l of out.split('\n')) { const i = l.indexOf('\t'); if (i > 0) m.set(l.slice(0, i), l.slice(i + 1)); }
  return m;
}

// ---------------------------------------------------------------- units
const table = tsv(path.join(HERE, 'data', 'retval_table.tsv')).slice(1);   // header 除去
const matrix = tsv(path.join(HERE, 'data', 'api_matrix.tsv'));
const apiInfo = new Map(matrix.map((r) => [r[0], { dll: r[1], group: r[2], gate: r[3], impl: r[4], gpa: r[5] }]));
console.log(`[units] 期待値表 ${table.length} 行 / API 表 ${matrix.length} 行`);

function unitRun(label, bin) {
  const r = run(bin);
  ok(r.status === 0, `${label}: 異常終了 status=${r.status} ${r.stderr.slice(-200)}`);
  const got = parseKV(r.stdout);
  const ex = run(bin, ['exit']);
  got.set('E01.01', `exit=${ex.status} hook=${/exit hook code=5/.test(ex.stderr) ? 1 : 0}`);
  let mism = 0;
  for (const [id, , , exp] of table) {
    if (!got.has(id)) { ok(false, `${label}: 行が出力されない ${id}`); mism++; continue; }
    if (got.get(id) !== exp) { ok(false, `${label}: ${id}\n      期待: ${exp}\n      実測: ${got.get(id)}`); mism++; }
    else checks++;
  }
  for (const id of got.keys()) if (!table.some((t) => t[0] === id)) ok(false, `${label}: 表に無い行が出力された ${id}`);
  console.log(`  ${label}: ${table.length - mism}/${table.length} 行一致`);
  summary[`units_${label}`] = { rows: table.length, matched: table.length - mism };
  return got;
}
unitRun('ST', path.join(WORK, 'units_st.cjs'));
if (existsSync(path.join(WORK, 'units_mt.cjs'))) unitRun('MT', path.join(WORK, 'units_mt.cjs'));

// 表の健全性: 全 API 行が matrix に存在 / matrix の全 API が 1 行以上の表行を持つ
const tableApis = new Set();
for (const [id, apis] of table) for (const a of apis.split(',')) { tableApis.add(a); ok(apiInfo.has(a), `表 ${id} の API ${a} が api_matrix に無い`); }
for (const [api] of matrix) ok(tableApis.has(api), `api_matrix の ${api} を検証する表行が無い`);

// ---------------------------------------------------------------- diff (baseline = shimx 単体)
console.log('[diff] shimx 単体 (trust_ok のみ) との差分を実測');
const base = parseKV(run(path.join(WORK, 'base_st.cjs')).stdout);
{
  const ex = run(path.join(WORK, 'base_st.cjs'), ['exit']);
  base.set('E01.01', `exit=${ex.status} hook=${/exit hook code=5/.test(ex.stderr) ? 1 : 0}`);
}
const status = new Map();   // id -> MATCH | DIFF | MISSING
const lines = ['id\tapis\tgate\tstatus\texpected\tshimx_only'];
for (const [id, apis, gate, exp] of table) {
  const b = base.get(id);
  const st = b === undefined ? 'MISSING' : b === exp ? 'MATCH' : 'DIFF';
  status.set(id, st);
  lines.push([id, apis, gate, st, exp, b === undefined ? '(API が存在しない)' : b].join('\t'));
}
writeFileSync(path.join(HERE, 'data', 'diff_table.tsv'), lines.join('\n') + '\n');
const cnt = { MATCH: 0, DIFF: 0, MISSING: 0 };
for (const s of status.values()) cnt[s]++;
console.log(`  行: MATCH ${cnt.MATCH} / DIFF ${cnt.DIFF} / MISSING ${cnt.MISSING} (計 ${table.length})`);
summary.diff_rows = cnt;
const perApi = new Map();   // api -> {rows, match, diff, missing}
for (const [id, apis] of table) for (const a of apis.split(',')) {
  const e = perApi.get(a) || { rows: 0, MATCH: 0, DIFF: 0, MISSING: 0 };
  e.rows++; e[status.get(id)]++; perApi.set(a, e);
}
const implCount = {};
for (const [api, info] of apiInfo) {
  implCount[info.impl] = (implCount[info.impl] || 0) + 1;
  const e = perApi.get(api);
  if (!e) continue;
  if (['shimx', 'shimx+count', 'cross-ref'].includes(info.impl)) ok(e.DIFF === 0, `${api}: impl=${info.impl} だが shimx 単体と食い違う行がある (${JSON.stringify(e)})`);   // MISSING = winstubs 独自機能の追加行 (shimx 側に API が無いのではない)
  else ok(e.DIFF + e.MISSING > 0, `${api}: impl=${info.impl} だが shimx 単体で既に全行一致 → 差分実装は不要 (${JSON.stringify(e)})`);
}
summary.impl_count = implCount;
console.log(`  impl 内訳: ${JSON.stringify(implCount)}`);

// ---------------------------------------------------------------- link
console.log('[link] リンクテスト');
for (const m of ['st', 'mt']) {
  const f = path.join(WORK, `probe_${m}.cjs`);
  if (!existsSync(f)) continue;
  const r = run(f);
  ok(r.status === 0, `probe_${m}: 異常終了 ${r.status} ${r.stderr.slice(-200)}`);
  const rows = new Map(r.stdout.split('\n').filter(Boolean).map((l) => { const c = l.split('\t'); return [c[0], c.slice(1)]; }));
  let good = 0;
  for (const [api, info] of apiInfo) {
    const v = rows.get(api);
    if (!ok(v, `probe_${m}: ${api} の行が無い`)) continue;
    const linked = v[0] === 'linked=1', gpa = v[1].slice(4), same = v[2].slice(5);
    const g = ok(linked, `probe_${m}: ${api} がリンクされていない`) &&
      ok(gpa === info.gpa, `probe_${m}: ${api} GetProcAddress=${gpa} (期待 ${info.gpa})`) &&
      ok(info.gpa !== 'y' || same === '1', `probe_${m}: ${api} GetProcAddress がリンク時アドレスと異なる (--wrap 非経由?)`);
    if (g) good++;
  }
  console.log(`  probe_${m}: ${good}/${apiInfo.size} API リンク可 + GetProcAddress 整合`);
  summary[`link_${m}`] = { ok: good, total: apiInfo.size };
}
{
  const f = path.join(WORK, 'probe_base.undef.txt');
  if (existsSync(f)) {
    const undef = new Set(readFileSync(f, 'utf8').split('\n').filter(Boolean));
    undef.delete('winstubs_init');
    const want = new Set();
    for (const [api, info] of apiInfo) if (['new', 'weak-new', 'lift-bridge'].includes(info.impl)) want.add(api === 'cpuid' ? 'winstubs_cpuid' : api);
    const miss = [...want].filter((x) => !undef.has(x)), extra = [...undef].filter((x) => !want.has(x));
    ok(miss.length === 0, `shimx 単体で解決済みなのに new 宣言: ${miss}`);
    ok(extra.length === 0, `shimx 単体で未解決なのに new 宣言が無い: ${extra}`);
    console.log(`  shimx 単体で未解決 ${undef.size} 本 == new 宣言 ${want.size} 本 (一致=${miss.length === 0 && extra.length === 0})`);
    summary.shimx_only_unresolved = [...undef].sort();
  }
}

// ---------------------------------------------------------------- boot
console.log('[boot] 起動シーケンス e2e');
{
  const seed = JSON.parse(readFileSync(SEED, 'utf8'));
  const lines2 = [];
  for (const hive of ['HKCU', 'HKLM']) {
    for (const [key, vals] of Object.entries(seed[hive] || {})) {
      for (const [name, def] of Object.entries(vals)) {
        let v = def.v;
        if (typeof v === 'string') v = v.replace('${MACHINE_GUID}', '7f3c2d1e-5a6b-4c8d-9e0f-1a2b3c4d5e6f' /* vreg が生成する per-profile GUID のスタンドイン */);
        lines2.push([hive, key, name, def.t, String(v)].join('\t'));
      }
    }
  }
  const f = path.join(WORK, 'boot_st.cjs');
  const factory = require(f);
  const out = [], err = [];
  const mod = await factory({ noInitialRun: true, print: (l) => out.push(l), printErr: (l) => err.push(l) });
  mod.FS.writeFile('/seed.tsv', lines2.join('\n') + '\n');
  let code = 0;
  try { mod.callMain(['/seed.tsv']); } catch (e) { code = e && e.status !== undefined ? e.status : 99; if (code === 99) err.push(String(e)); }
  ok(code === 0, `boot: 異常終了 code=${code} ${err.slice(-3).join('|')}`);
  const got = parseKV(out.join('\n'));
  const exp = tsv(path.join(HERE, 'data', 'boot_expect.tsv')).slice(1);
  let n = 0;
  for (const [step, , want] of exp) {
    if (!ok(got.has(step), `boot: ${step} が出力されない`)) continue;
    if (ok(got.get(step) === want, `boot ${step}\n      期待: ${want}\n      実測: ${got.get(step)}`)) n++;
  }
  console.log(`  boot ステップ ${n}/${exp.length} 一致 (seed ${lines2.length} 値投入)`);
  summary.boot = { steps: exp.length, matched: n };
  writeFileSync(path.join(WORK, 'boot.out'), out.join('\n') + '\n');
}

writeFileSync(path.join(WORK, 'summary.json'), JSON.stringify({ checks, fails, ...summary }, null, 1));
console.log(fails === 0 ? `\nALL PASS (checks=${checks})` : `\nFAILED (fails=${fails} / checks=${checks})`);
process.exit(fails === 0 ? 0 : 1);
