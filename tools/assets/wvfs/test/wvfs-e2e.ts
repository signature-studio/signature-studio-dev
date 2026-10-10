// wvfs (書込可能 OPFS VFS) の 1 コマンド e2e。
//   node wvfs/test/wvfs-e2e.ts [--keep] [--fresh]
// **実ディスクの Chrome プロファイル必須** (tmpfs /tmp プロファイルでは OPFS SyncAccessHandle 書込が
// 壊れる実績あり — CAB-21 REPORT §3 / tools/hosting REPORT §6-8)。プロファイルは
// wvfs/work/chrome-profiles/wvfs-e2e-*/ を 3 起動で使い回し、OPFS のプロセス跨ぎ永続を検証する:
//   run1 seed  : pathreg 経路で書込 (writeFileSync / fd 部分書込) → onYield/onPageHide で flush
//   run2 verify: 再起動後に全ファイル sha256 照合 → torn tail 復元 / superblock 復旧 / compaction
//   run3 verify2: compaction 後の別プロセス再起動で再照合
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFileSync, type ChildProcess } from 'node:child_process';
import { build } from 'esbuild';
import { spawnServer } from '../../test/spawn-server.ts';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..'); // tools/assets/wvfs
const KEEP = process.argv.includes('--keep');
const CHROME = process.env.CHROME ?? 'google-chrome';

// ---- 1. bundle ----
const APP = path.join(root, 'work', 'app-wvfs');
fs.rmSync(APP, { recursive: true, force: true });
fs.mkdirSync(APP, { recursive: true });
await build({
  entryPoints: { main: 'wvfs/test/wvfs-page/main.ts', 'wvfs-worker': 'wvfs/test/wvfs-page/wvfs-worker.ts' },
  outdir: APP,
  bundle: true,
  format: 'esm',
  target: 'es2022',
  platform: 'browser',
  external: ['node:*'],
  logLevel: 'warning',
  absWorkingDir: path.join(root, '..'), // tools/assets
});
fs.copyFileSync(path.join(root, 'test/wvfs-page/index.html'), path.join(APP, 'index.html'));

function run(cmd: string, args: string[]): void {
  try {
    execFileSync(cmd, args, { stdio: 'inherit' });
  } catch (e: any) {
    throw new Error(`${path.basename(cmd)} failed (exit ${e.status})`);
  }
}

// ---- 2. server + chrome ----
run(process.execPath, [path.join(root, 'test/wvfs-node.test.ts')]);
run(process.execPath, [path.join(root, 'test/wvfs-emscripten.test.ts')]);
const srv = await spawnServer(APP, { appDir: APP });
const profDir = path.join(root, 'work', 'chrome-profiles');
fs.mkdirSync(profDir, { recursive: true });
if (A.fresh) {
  for (const d of fs.readdirSync(profDir)) if (d.startsWith('wvfs-e2e-')) fs.rmSync(path.join(profDir, d), { recursive: true, force: true });
}
const existing = fs.readdirSync(profDir).filter((d) => d.startsWith('wvfs-e2e-'));
const udd = existing.length ? path.join(profDir, existing[0]) : fs.mkdtempSync(path.join(profDir, 'wvfs-e2e-'));
console.log(`chrome profile (real disk): ${udd}`);

async function runChrome(phase: string): Promise<any> {
  const url = `${srv.url}/app/index.html?phase=${phase}`;
  // HTTP ディスクキャッシュだけ起動毎に新しく (user-data-dir の OPFS/IDB は使い回し)
  const dcd = fs.mkdtempSync(path.join(profDir, 'diskcache-'));
  const cp: ChildProcess = spawn(
    CHROME,
    [
      '--headless=new',
      '--no-sandbox',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      `--user-data-dir=${udd}`,
      `--disk-cache-dir=${dcd}`,
      '--remote-debugging-port=0',
      url,
    ],
    { stdio: ['ignore', 'ignore', 'ignore'], detached: true }
  );
  try {
    return await srv.waitReport(240000);
  } finally {
    try {
      process.kill(-cp.pid!, 'SIGKILL');
    } catch {}
    if (!KEEP) fs.rmSync(dcd, { recursive: true, force: true });
    await new Promise((r) => setTimeout(r, 400));
  }
}

let failed = 0;
const must = (cond: boolean, msg: string) => {
  console.log(cond ? '  ok  ' : '  FAIL', msg);
  if (!cond) failed++;
};

// run1: seed
console.log('[chrome:seed]');
const seed = await runChrome('seed');
if (!seed.ok) {
  console.log('  FAIL report:', seed.error, 'stage=', seed.stage);
  fs.writeFileSync(path.join(root, 'work/results-wvfs-e2e.json'), JSON.stringify({ seed }, null, 1));
  await srv.close();
  process.exit(1);
}
console.log(`  report: files=${seed.res.files.length} caseOk=${seed.res.caseOk} journal=${JSON.stringify(seed.res.journal)} storage=${JSON.stringify(seed.res.storage)}`);
must(seed.res.files.length >= 6, `seed wrote ${seed.res.files.length} files (>=6)`);
must(seed.res.files.every((f: any) => f.sha256?.length === 64 && f.size >= 0), 'all files have sha256/size');
must(seed.res.caseOk === true, 'case-insensitive read at seed');
must(Object.values(seed.res.routes).every((v: any) => v && (v.mount === 'home' || v.mount === 'tmp')), 'pathreg routes → home/tmp mounts');
must((seed.res.journal.home.files ?? 0) >= 5 && (seed.res.journal.tmp.files ?? 0) >= 1, 'journal index populated (home/tmp)');
must((seed.res.storage.quota ?? 0) > 0, `storage.estimate quota=${seed.res.storage.quota}`);
fs.writeFileSync(path.join(APP, 'wvfs-expected.json'), JSON.stringify({ files: seed.res.files }, null, 1));

// run2: verify + torn + slot + compact
console.log('[chrome:verify] (process restart, OPFS persists)');
const verify = await runChrome('verify');
if (!verify.ok) {
  console.log('  FAIL report:', verify.error, 'stage=', verify.stage);
  fs.writeFileSync(path.join(root, 'work/results-wvfs-e2e.json'), JSON.stringify({ seed, verify }, null, 1));
  await srv.close();
  process.exit(1);
}
console.log(`  report: mismatches=${verify.res.mismatches.length} torn=${JSON.stringify(verify.res.torn)} slot=${JSON.stringify(verify.res.slot)} compact=${JSON.stringify(verify.res.compact)} post=${JSON.stringify(verify.res.postCompact)}`);
must(verify.res.mismatches.length === 0, `reload: all ${seed.res.files.length} files match sha256 (process restart)`);
must(verify.res.caseOk === true, 'reload: case-insensitive read');
must(verify.res.torn?.detected === 1 && verify.res.torn?.bytesOk && verify.res.torn?.manifestOk, 'torn tail detected (1) and state intact');
must(verify.res.slot?.journalId >= 1 && verify.res.slot?.intact, 'superblock slot corruption recovered via other slot');
must(verify.res.compact?.shrunk && verify.res.compact?.before > 5 * 2 ** 20, `compaction shrunk journal (${verify.res.compact?.before} → ${verify.res.compact?.after})`);
must(verify.res.compact?.churnLen === 128 * 1024 && verify.res.postCompact?.churnOk && verify.res.postCompact?.fstOk, 'compaction: data + plugin db intact (reload)');
must(verify.res.postCompact?.dirs === 2, 'compaction: OTT dir entries (OTT.fst + OTT.nfo) survive');
fs.writeFileSync(path.join(root, 'work/results-wvfs-e2e.json'), JSON.stringify({ seed, verify }, null, 1));

// run3: verify2 (compaction 後の別プロセス)
console.log('[chrome:verify2] (after compaction, new process)');
const verify2 = await runChrome('verify');
if (!verify2.ok) {
  console.log('  FAIL report:', verify2.error, 'stage=', verify2.stage);
  failed++;
} else {
  console.log(`  report: mismatches=${verify2.res.mismatches.length} journal=${JSON.stringify(verify2.res.journal)}`);
  must(verify2.res.mismatches.length === 0, 'post-compaction reload: all files match sha256');
  must(verify2.res.journal.home.journalId >= 2, `active journal after compaction (id=${verify2.res.journal.home.journalId})`);
  fs.writeFileSync(path.join(root, 'work/results-wvfs-e2e.json'), JSON.stringify({ seed, verify, verify2 }, null, 1));
}

await srv.close();
console.log(failed ? `FAILED: ${failed}` : 'ALL PASS');
process.exit(failed ? 1 : 0);
