#!/usr/bin/env node
// glue_e2e.ts — glue の 1 コマンド e2e (CAB-101)。
//   node tools/startup/glue/host/glue_e2e.ts
//
// 1. build (ST/MT) — 新規 .c を wasm 化
// 2. C 単体 (ST/MT)  … 初期化順序規約・THostInstance・CreateFruityInstance スタブ・trace 順序
// 3. TS 単体         … 段階の独立呼出・flush フック・wvfs mount・pump RING・trace 突合
// 4. SIGKILL 跨ぎ e2e … seed プロセスを kill -9 で殺し、別プロセスで全域 sha256 照合
// 5. trace 監査      … username=webstudio で C:\Users\user 残存 0 / /c/Users/ 残存 0
import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GLUE = path.resolve(HERE, '..');
const REPO = path.resolve(GLUEdir(), '../../..');
function GLUEdir() { return GLUE; }
const WORK = path.join(GLUEdir(), 'work/e2e');

const t0 = Date.now();
const la = () => fs.readFileSync('/proc/loadavg', 'utf8').split(' ').slice(0, 3).join(' ');
const mark = (s: string) => console.log(`[glue-e2e] (${((Date.now() - t0) / 1000).toFixed(1)}s, load ${la()}) ${s}`);
const sh = (cmd: string, args: string[], cwd = GLUEdir()) => execFileSync(cmd, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8' });

let failed = 0;
const ok = (c: boolean, m: string) => { console.log(c ? '  ok  ' : '  FAIL', m); if (!c) failed++; };

fs.rmSync(WORK, { recursive: true, force: true });
fs.mkdirSync(WORK, { recursive: true });

mark(`start load=${la()}`);
mark('1/5 build (ST/MT objects + glue module + unit binaries)');
sh('bash', ['host/build.sh', 'objs', 'ST']);
sh('bash', ['host/build.sh', 'objs', 'MT']);
sh('bash', ['host/build.sh', 'link', 'ST', 'work/glue_mod.js', 'gluemod']);
fs.renameSync(path.join(GLUEdir(), 'work/glue_mod.js'), path.join(GLUEdir(), 'work/glue_mod.mjs'));
sh('bash', ['host/build.sh', 'link', 'ST', 'work/unit_st.js', 'unit', 'test/glue_unit.c']);
fs.renameSync(path.join(GLUEdir(), 'work/unit_st.js'), path.join(GLUEdir(), 'work/unit_st.cjs'));
sh('bash', ['host/build.sh', 'link', 'MT', 'work/unit_mt.js', 'unit', 'test/glue_unit.c']);
fs.renameSync(path.join(GLUEdir(), 'work/unit_mt.js'), path.join(GLUEdir(), 'work/unit_mt.cjs'));
mark('  build ok');

mark('2/5 C 単体 (ST=HOSTED / MT=ATOMIC 既定)');
for (const mode of ['ST', 'MT']) {
  const out = sh('node', [`work/unit_${mode.toLowerCase()}.cjs`]);
  const pass = /pass=(\d+) fail=(\d+)/.exec(out);
  ok(!!pass && pass[2] === '0', `C unit ${mode}: ${pass ? `${pass[1]} checks, ${pass[2]} fail` : 'no result'}`);
}

mark('3/5 TS 単体 (順序規約 / flush フック / wvfs mount / pump RING / trace 突合)');
const tsOut = sh('node', ['test/glue_unit.ts']);
const ts = /\(pass=(\d+) fail=(\d+)\)/.exec(tsOut);
ok(!!ts && ts[2] === '0', `TS unit: ${ts ? `${ts[1]} checks, ${ts[2]} fail` : 'no result'}`);

mark('4/5 SIGKILL 跨ぎ e2e (seed → kill -9 → verify)');
{
  const seedDir = path.join(WORK, 'seed');
  fs.mkdirSync(seedDir, { recursive: true });
  const seed = spawn(process.execPath, [path.join(GLUEdir(), 'test/glue_child.ts'), '--dir', seedDir, '--mode', 'seed'], { cwd: GLUEdir(), stdio: ['ignore', 'pipe', 'pipe'], detached: true });
  let seedOut = '';
  let killed = 'none';
  await new Promise<void>((res) => {
    seed.stdout.on('data', (d) => {
      seedOut += d;
      if (seedOut.includes('SEED-FLUSHED')) {           // マーカーで待つ (sleep による固定待機はしない)
        try { process.kill(-seed.pid!, 'SIGKILL'); killed = 'group'; } catch { try { process.kill(seed.pid!, 'SIGKILL'); killed = 'pid'; } catch { killed = 'failed'; } }
      }
    });
    seed.on('exit', (code, sig) => { console.log(`  seed exit code=${code} signal=${sig} kill=${killed}`); res(); });
  });
  ok(killed !== 'failed', `seed killed with SIGKILL (${killed})`);
  {
    const expected = JSON.parse(fs.readFileSync(path.join(seedDir, 'expected.json'), 'utf8'));
    ok(expected.files.length === 3, `seed wrote ${expected.files.length} files before SIGKILL`);
  }
  const ver = spawn(process.execPath, [path.join(GLUEdir(), 'test/glue_child.ts'), '--dir', seedDir, '--mode', 'verify'], { cwd: GLUEdir(), stdio: ['ignore', 'pipe', 'pipe'] });
  let verOut = '';
  ver.stdout.on('data', (d) => (verOut += d));
  const verCode: number = await new Promise((res) => ver.on('exit', (c) => res(c ?? 1)));
  const rep = /"ok":(true|false),"checked":(\d+),"mismatches":(\d+),"regOk":(true|false)/.exec(verOut);
  ok(!!rep && rep[1] === 'true', `verify: checked=${rep?.[2]} mismatches=${rep?.[3]} regOk=${rep?.[4]}`);
  ok(verCode === 0, `verify child exit code = ${verCode}`);

  // ---- 陰性対照: flush 点を呼ばずに SIGKILL → 失われる (規則 41) ----
  const ctlDir = path.join(WORK, 'control-noflush');
  fs.mkdirSync(ctlDir, { recursive: true });
  const ctl = spawn(process.execPath, [path.join(GLUEdir(), 'test/glue_child.ts'), '--dir', ctlDir, '--mode', 'seed', '--noflush', '1'], { cwd: GLUEdir(), stdio: ['ignore', 'pipe', 'pipe'], detached: true });
  let ctlOut = '';
  let ctlKilled = 'none';
  await new Promise<void>((res) => {
    ctl.stdout.on('data', (d) => {
      ctlOut += d;
      if (ctlOut.includes('SEED-FLUSHED')) { try { process.kill(-ctl.pid!, 'SIGKILL'); ctlKilled = 'group'; } catch { try { process.kill(ctl.pid!, 'SIGKILL'); ctlKilled = 'pid'; } catch { ctlKilled = 'failed'; } } }
    });
    ctl.on('exit', (_c, sig) => { console.log(`  control exit signal=${sig} kill=${ctlKilled}`); res(); });
  });
  const cver = spawn(process.execPath, [path.join(GLUEdir(), 'test/glue_child.ts'), '--dir', ctlDir, '--mode', 'verify'], { cwd: GLUEdir(), stdio: ['ignore', 'pipe', 'pipe'] });
  let cverOut = '';
  cver.stdout.on('data', (d) => (cverOut += d));
  await new Promise((res) => cver.on('exit', () => res(0)));
  const crep = /"ok":(true|false),"checked":(\d+),"mismatches":(\d+),"regOk":(true|false)/.exec(cverOut);
  // 識別信号は regOk: flush 点を呼ばないと RegBridge.save が走らず永続レコードが失われる。
  // (ファイル側 mismatches=0 も想定どおり: NodeBackend は fs.writeSync で OS ページキャッシュに
  //  書くため、SIGKILL (OS 停止ではない) では落ちない。OS クラッシュ耐性は wvfs 既存検証の範囲)
  ok(!!crep && crep[1] === 'false' && crep[4] === 'false' && crep[3] === '0',
     `control (no flush): mismatches=${crep?.[3]} regOk=${crep?.[4]} - registry lost (flush point is the contract)`);
}

mark('5/5 trace 監査 (username=webstudio / C:\\Users\\user 残存 0)');
{
  // 監査は子プロセスの trace を再利用しない (SIGKILL で失われる)。独立に 1 回起動して集計する。
  const auditDir = path.join(WORK, 'audit');
  fs.mkdirSync(auditDir, { recursive: true });
  const out = sh('node', ['-e', `
    const { GlueHost } = await import(${JSON.stringify(path.join(GLUEdir(), 'host/glue_host.ts'))});
    const mod = await import(${JSON.stringify(path.join(GLUEdir(), 'work/glue_mod.mjs'))});
    const m = await mod.default();
    const h = new GlueHost(m, { username: 'webstudio', workDir: ${JSON.stringify(auditDir)} });
    await h.runAll('?open=Demo.flp');
    const t = h.traceText();
    const n = (s) => (t.match(new RegExp(s.replace(/[.*+?^\${}()|[\\]\\\\]/g, '\\\\$&'), 'g')) || []).length;
    console.log(JSON.stringify({
      lines: h.trace().length, stages: h.stages.length,
      usersUser: n('C:\\\\\\\\Users\\\\\\\\user'), residual: n('-> 0 /c/Users/'),
      home: n('/c/home'), tmp: n('/c/tmp'), fl: n('/fl/'),
      violations: m._glue_order_violations(),
    }));
  `]);
  const a = JSON.parse(out.trim().split('\n').pop()!);
  ok(a.usersUser === 0, `C:\\Users\\user residue == 0 (${a.usersUser})`);
  ok(a.residual === 0, `residual /c/Users/ mappings == 0 (${a.residual})`);
  ok(a.home >= 1 && a.tmp >= 1 && a.fl >= 1, `mapping recorded home=${a.home} tmp=${a.tmp} fl=${a.fl}`);
  ok(a.violations === 0, `order violations == 0 (${a.violations})`);
  ok(a.stages === 10, `stages executed == 10 (${a.stages})`);
}

mark(`done in ${((Date.now() - t0) / 1000).toFixed(1)}s (load now ${la()})`);
console.log(failed === 0 ? '[glue-e2e] ALL PASS' : `[glue-e2e] FAIL (${failed})`);
process.exit(failed === 0 ? 0 : 1);
