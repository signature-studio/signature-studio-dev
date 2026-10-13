// headless Chrome で VFS を実行: OPFS SyncAccessHandle キャッシュ / SAB 同期ローダ / sync XHR フォールバック / cross-origin 配信 / 再起動(warm)。
//   node test/browser-test.ts --pkg work/pkg-t1 [--latency 0] [--mbps 0] [--out work/results-chrome.json]
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { build } from 'esbuild';
import { spawnServer } from './spawn-server.ts';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..');
const PKG = path.resolve(root, A.pkg ?? 'work/pkg-t1');
const INV = path.resolve(root, A.inv ?? 'work/inv_win.jsonl');
const OUT = path.resolve(root, A.out ?? 'work/results-chrome.json');
const LAT = Number(A.latency ?? 0);
const MBPS = Number(A.mbps ?? 0);
const NFILES = Number(A.sample ?? 150);
const EXTRA = A.verify === '0' ? '&verify=0' : '';
const RA = A.ra ? `&ra=${A.ra}` : '';
const APP = path.join(root, 'work', 'app');
const CHROME = process.env.CHROME ?? 'google-chrome';

// ---- bundle ----
fs.rmSync(APP, { recursive: true, force: true });
fs.mkdirSync(APP, { recursive: true });
await build({
  entryPoints: { main: 'test/browser/main.ts', 'engine-worker': 'test/browser/engine-worker.ts', 'probe-worker': 'test/browser/probe-worker.ts', 'fetch-worker': 'vfs/fetch-worker.ts' },
  outdir: APP,
  bundle: true,
  format: 'esm',
  target: 'es2022',
  platform: 'browser',
  external: ['node:*'],
  logLevel: 'warning',
  absWorkingDir: root,
});
fs.copyFileSync(path.join(root, 'test/browser/index.html'), path.join(APP, 'index.html'));

// ---- expected.json (inventory の sha256 を正とする) ----
const latest = JSON.parse(fs.readFileSync(path.join(PKG, 'latest.json'), 'utf8'));
const zlib = await import('node:zlib');
const manifest = JSON.parse(zlib.brotliDecompressSync(fs.readFileSync(path.join(PKG, latest.manifest))).toString());
const present = (p: string) => {
  let d: any = manifest.tree;
  for (const part of p.split('/')) {
    if (!d || Array.isArray(d)) return false;
    d = d[part];
  }
  return d !== undefined;
};
const inv = fs.readFileSync(INV, 'utf8').trim().split('\n').map((l) => JSON.parse(l)).filter((e) => e.cls !== 'skip' && e.cat !== 'exec' && e.size > 0 && present(e.p));
const stepN = Math.max(1, Math.floor(inv.length / NFILES));
const files = inv.filter((_, i) => i % stepN === 0).map((e) => ({ p: e.p, size: e.size, sha: e.sha }));
const big = [...inv].sort((a, b) => b.size - a.size).slice(0, 2).map((e) => ({ p: e.p, size: e.size, sha: e.sha }));
fs.writeFileSync(path.join(APP, 'expected.json'), JSON.stringify({ files, big, boot: true }));
console.log(`expected: ${files.length} files, big ${big.map((b) => b.p + ' ' + (b.size / 1e6).toFixed(1) + 'MB').join(', ')}`);

// ---- servers: A = app + chunks (same-origin), B = chunks only (cross-origin) ----
const srvA = await spawnServer(PKG, { appDir: APP });
const srvB = await spawnServer(PKG);
for (const s of [srvA, srvB]) await s.shape(LAT, MBPS);

// Chrome プロファイルは実ディスク (work/ 配下, gitignore) に置く。/tmp は tmpfs で
// OPFS SyncAccessHandle の書込が InvalidStateError で壊れる (tools/hosting/REPORT.md §6-8 実測)。
fs.mkdirSync(path.join(root, 'work/chrome-profiles'), { recursive: true });
const udd = fs.mkdtempSync(path.join(root, 'work/chrome-profiles/browser-test-'));
async function runChrome(query: string): Promise<any> {
  const url = `${srvA.url}/app/index.html?${query}${EXTRA}${RA}`;
  const cp = spawn(CHROME, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check', `--user-data-dir=${udd}`, '--remote-debugging-port=0', url], { stdio: ['ignore', 'ignore', 'ignore'], detached: true });
  try {
    return await srvA.waitReport(120000);
  } finally {
    try {
      process.kill(-cp.pid!, 'SIGKILL');
    } catch {}
    await new Promise((r) => setTimeout(r, 300));
  }
}

const base = encodeURIComponent(srvB.url + '/');
const out: Record<string, any> = { pkg: PKG, shaping: { latencyMs: LAT, mbps: MBPS }, runs: {} };
let failed = 0;
const must = (c: boolean, m: string) => {
  console.log(c ? '  ok  ' : '  FAIL', m);
  if (!c) failed++;
};
for (const [name, query] of [
  ['cold', `phase=cold&base=${base}`],
  ['warm', `phase=warm&base=${base}`],
  ['xhr-cold', `phase=xhr-cold&loader=xhr`],
] as const) {
  await srvA.reset();
  await srvB.reset();
  console.log(`[chrome:${name}]`);
  const rep = await runChrome(query);
  const sa = await srvA.stats();
  const sb = await srvB.stats();
  if (!rep.ok) {
    console.log(rep.error);
    failed++;
    out.runs[name] = rep;
    continue;
  }
  const r = rep.res;
  r.serverChunkRequests = (sa.byKind.chunk ?? 0) + (sb.byKind.chunk ?? 0);
  r.serverBytes = sa.bytes + sb.bytes;
  out.runs[name] = r;
  must(r.statOk === `${files.length}/${files.length}`, `stat ${r.statOk}`);
  must(r.content.mismatches === 0, `sha256 match (${r.content.files} files, ${r.content.MB} MB, ${r.content.ms} ms)`);
  must(r.enoent === 'ENOENT', 'ENOENT');
  must(r.opfsOpened, 'OPFS SyncAccessHandle opened (cache kind=' + r.cacheKind + ')');
  if (name !== 'xhr-cold') must(r.workerIsolated && r.sab, 'crossOriginIsolated + SAB in worker');
  if (name === 'cold') must(r.secondHandleBlocked === true, 'second OPFS handle blocked while first open (multi-tab → fallback path)');
  if (name === 'warm') {
    must(r.cacheScannedSlots > 0, `warm: ${r.cacheScannedSlots} slots recovered from OPFS`);
    // 全件 (NFILES >= inv 件数) は OPFS の slot 上限 (cache) を超えるため warm でも再取得が起きる。
    // 上限判定は全件のときは行わず、件数は REPORT に実測値として残す。
    if (NFILES < inv.length) must(r.serverChunkRequests <= 2, `warm: server chunk requests = ${r.serverChunkRequests} (sequential big files may add)`);
    else console.log(`  info warm: server chunk requests = ${r.serverChunkRequests} (full set > cache, not asserted)`);
  }
  console.log(JSON.stringify({ content: r.content, missLatencyMs: r.missLatencyMs, sequential: r.sequential, preloadBoot: r.preloadBoot, serverChunkRequests: r.serverChunkRequests, fetcher: r.fetcher, vfsStats: r.vfsStats }, null, 1));
}
out.failed = failed;
fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
await srvA.close();
await srvB.close();
fs.rmSync(udd, { recursive: true, force: true });
console.log(failed ? `FAILED: ${failed}` : 'ALL PASS');
process.exit(failed ? 1 : 0);
