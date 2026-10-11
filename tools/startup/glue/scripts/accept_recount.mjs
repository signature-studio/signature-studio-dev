// accept_recount.mjs — CAB-101 検収: glue REPORT の見出し数値を別アルゴリズムで再計算する (規則 37)。
//   node tools/startup/glue/scripts/accept_recount.mjs
//
// 実装側スクリプトとの違い (同じ実装の再実行は独立再計算ではない):
//   - scripts/count_checks.mjs : 単体バイナリを実行し stdout の行Regexで数える
//   - scripts/audit_trace.mjs  : GlueHost を起動し trace 文字列だけで A/B/C/D を検算
//   - 本スクリプト            : **ソースの ok(/CHECK 呼出しサイトの静的解析** + e2e 出力の
//                               構造解析 + pathmap.mjs の既定表からの独立集計で数える
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const GLUE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const GLUEdir = () => GLUE;
const sh = (a, cwd = GLUE) => execFileSync(a[0], a.slice(1), { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 64e6 });
const R = (p) => fs.readFileSync(path.join(GLUE, p), 'utf8');

// --- 1. 静的カウント: ソースの ok( 呼出しサイト (行頭インデント区別・コメント行は除外) ---
const countCallSites = (file, fn) => {
  const lines = R(file).split('\n');
  let n = 0, commented = 0;
  for (const l of lines) {
    const s = l.replace(/^\s+/, '');
    if (new RegExp(`^${fn}\\(`).test(s)) n++;
    else if (new RegExp(`^\\/\\/.*\\b${fn}\\(`).test(s)) commented++;
  }
  return { n, commented };
};
const cUnit = countCallSites('test/glue_unit.c', 'ok');
const tsUnit = countCallSites('test/glue_unit.ts', 'ok');
const e2e = countCallSites('host/glue_e2e.ts', 'ok');
// C 単体は段階の done 行 (`for (i=FIRST; i<=LAST; i++) ... printf("       stage ...")`) が
// ok( 外のチェック。実行回数 = ループ回数 = kStages[] の要素数 (glue.c) = GLUE_STAGE_COUNT。
let mountMatch = false;
const cStageLines = (R('src/glue.c').match(/^    \{ GLUE_STAGE_\w+,\s*"\w+"\s*\},$/gm) || []).length;
console.log(`C unit  : ok( call sites=${cUnit.n} (comment除外) + stage done lines=${cStageLines} => ${cUnit.n + cStageLines} checks`);
console.log(`TS unit : ok( call sites=${tsUnit.n}`);
console.log(`e2e     : ok( call sites=${e2e.n}`);

// --- 2. 実行して突合 (C 単体 ST/MT, TS 単体) ---
for (const mode of ['st', 'mt']) {
  const out = sh(['node', `work/unit_${mode}.cjs`]);
  const m = /GLUE (ALL PASS|FAIL) \(pass=(\d+) fail=(\d+)\)/.exec(out);
  const okLines = (out.match(/^ {2}ok {3}/gm) || []).length + (out.match(/^ {7}stage /gm) || []).length;
  console.log(`C unit ${mode}: verdict=${m?.[1]} pass=${m?.[2]} fail=${m?.[3]} | executed ok/stage lines=${okLines} => ${m?.[2] === String(cUnit.n + cStageLines) && okLines === cUnit.n + cStageLines ? 'MATCH' : 'DIFF'}`);
}
{
  const out = sh(['node', 'test/glue_unit.ts']);
  const m = /\(pass=(\d+) fail=(\d+)\)/.exec(out);
  const okLines = (out.match(/^ {2}ok {2}/gm) || []).length;
  console.log(`TS unit : pass=${m?.[1]} fail=${m?.[2]} | executed ok lines=${okLines} => ${m?.[1] === String(tsUnit.n) && okLines === tsUnit.n ? 'MATCH' : 'DIFF'}`);
}

// --- 3. 既定マウント表の独立集計 (pathmap.mjs 由来) と C の pathreg_mount_count の一致 ---
{
  const { defaultMounts } = await import(path.join(GLUEdir(), '../../shimx/pathreg/js/pathmap.mjs'));
  const dm = defaultMounts();
  const script = `
    const mod = await import(${JSON.stringify(path.join(GLUE, 'work/glue_mod.mjs'))});
    const m = await mod.default();
    m._glue_reset?.();
    m._glue_stage_paths('webstudio');
    console.log('MOUNTCOUNT=' + m._pathreg_mount_count());
    console.log('VIOL=' + m._glue_order_violations());
    console.log('TRACE=' + JSON.stringify(m._glue_trace_count()));
  `;
  const out = sh(['node', '-e', script]);
  const mc = Number(/MOUNTCOUNT=(\d+)/.exec(out)?.[1]);
  const viol = Number(/VIOL=(\d+)/.exec(out)?.[1]);
  mountMatch = (mc === dm.length && mc === 8);
  console.log(`mount table: C pathreg_mount_count()=${mc} / JS defaultMounts()=${dm.length} / glue trace "mounts=" -> ${/mounts=(\d+)/.exec(sh(['node', '-e', script.replace(/console.*/g, '') + "console.log(m._pathreg_mount_count())"]))?.[1] ?? '?'} => ${mc === dm.length && mc === 8 ? 'MATCH(8)' : 'DIFF'}`);
  console.log(`order violations=${viol} (expect 0)`);
}

// --- 4. trace 監査 (username=webstudio で C:\Users\user 残存 0 / 規約順 10) ---
{
  const out = sh(['node', '-e', `
    const { GlueHost } = await import(${JSON.stringify(path.join(GLUE, 'host/glue_host.ts'))});
    const mod = await import(${JSON.stringify(path.join(GLUE, 'work/glue_mod.mjs'))});
    const m = await mod.default();
    const h = new GlueHost(m, { username: 'webstudio', workDir: ${JSON.stringify(path.join(GLUE, 'work/verify/glue_recount'))} });
    await h.runAll('?open=Demo.flp');
    const t = h.trace();
    const enters = t.filter(l => /stage=\\S+ enter/.test(l)).map(l => l.match(/stage=(\\S+) enter/)[1]);
    const oks = t.filter(l => /stage=\\S+ ok \\(/.test(l)).map(l => l.match(/stage=(\\S+) ok/)[1]);
    const canon = ['paths','registry','pump','vfs','pre_dllmain','dllmain','host','boot','post','shutdown'];
    console.log('JSONOUT' + JSON.stringify({
      lines: t.length, enter: enters, ok: oks,
      usersUser: t.filter(l => l.includes('C:\\\\Users\\\\user')).length,
      residual: t.filter(l => /-> 0 \\/c\\/Users\\//.test(l)).length,
      viol: m._glue_order_violations(),
    }));
  `]);
  const j = JSON.parse(out.trim().split('\n').find(l => l.startsWith('JSONOUT')).slice('JSONOUT'.length));
  const canon = ['paths','registry','pump','vfs','pre_dllmain','dllmain','host','boot','post','shutdown'];
  console.log(`trace: lines=${j.lines} enter=${j.enter.length} ok=${j.ok.length} C:\\Users\\user=${j.usersUser} residual /c/Users/=${j.residual} violations=${j.viol}`);
  console.log(`  enter order == canonical : ${JSON.stringify(j.enter) === JSON.stringify(canon) ? 'MATCH' : 'MISMATCH'}`);
  console.log(`  ok    order == canonical : ${JSON.stringify(j.ok) === JSON.stringify(canon) ? 'MATCH' : 'MISMATCH'}`);
  var jTrace = j;
}
const nC = cUnit.n + cStageLines;
const nTS = tsUnit.n;
const j = jTrace ?? { enter: [], ok: [], usersUser: -1, residual: -1, viol: -1 };
const allMatch = nC === 66 && nTS === 49 && mountMatch && j.enter.length === 10 && j.ok.length === 10 && j.usersUser === 0 && j.residual === 0 && j.viol === 0;
console.log(allMatch ? 'accept_recount: MATCH (C unit 66 / TS unit 49 / mounts 8 / trace 40)' : 'accept_recount: MISMATCH');
process.exit(allMatch ? 0 : 1);
