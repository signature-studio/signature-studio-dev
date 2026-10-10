// asset ローダ (314MB 級 wasm) の 1 コマンド e2e。
//   node test/asset-e2e.ts [--keep] [--latency MS --mbps MBPS] [--corruptChunk N]
// 実ディスクの Chrome プロファイル (work/chrome-profiles/, gitignore) を 4 起動で使い回し、
// OPFS/IDB 永続を跨いで検証する (/tmp は tmpfs で OPFS SyncAccessHandle 書込が壊れるため禁止):
//   1. cold         : network から全 chunk 取得 → 連結 → compileStreaming → OPFS+IDB 保存
//   2. warm-netoff  : network 遮断でキャッシュのみ (chunk request 0) → compile
//   3. corrupt-opfs : OPFS 1 chunk 破損 → IDB から部分修復 (network 無し)
//   4. corrupt-both : OPFS+IDB 同一 chunk 破損 → network から再取得して修復
// 各シナリオ = Chrome 1 起動 + /__report ロングポール 1 本 (競合なし)。
// 全シナリオで連結結果の sha256 全体一致を検証する。
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { spawn, execFileSync, type ChildProcess } from 'node:child_process';
import { build } from 'esbuild';
import { spawnServer } from './spawn-server.ts';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..');
const LAT = Number(A.latency ?? 0);
const MBPS = Number(A.mbps ?? 0);
const KEEP = process.argv.includes('--keep');
const CORRUPT_CHUNK = Number(A.corruptChunk ?? 3);
const CHROME = process.env.CHROME ?? 'google-chrome';

// ---- 1. パッケージ (冪等) ----
console.log('[1/4] asset package');
run(process.execPath, [path.join(root, 'test/make-asset-pkg.ts')]);
const expected = JSON.parse(fs.readFileSync(path.join(root, 'work/asset-expected.json'), 'utf8'));
const PKG = path.resolve(root, expected.pkg);

// ---- 2. bundle ----
console.log('[2/4] bundle');
const APP = path.join(root, 'work', 'app-asset');
fs.rmSync(APP, { recursive: true, force: true });
fs.mkdirSync(APP, { recursive: true });
await build({
  entryPoints: { main: 'test/asset-page/main.ts', 'asset-worker': 'test/asset-page/asset-worker.ts' },
  outdir: APP,
  bundle: true,
  format: 'esm',
  target: 'es2022',
  platform: 'browser',
  external: ['node:*'],
  logLevel: 'warning',
  absWorkingDir: root,
});
fs.copyFileSync(path.join(root, 'test/asset-page/index.html'), path.join(APP, 'index.html'));
fs.copyFileSync(path.join(root, 'work/asset-expected.json'), path.join(APP, 'asset-expected.json'));

// manifest の chunk 数 (node 側で確認)
const latest = JSON.parse(fs.readFileSync(path.join(PKG, 'latest.json'), 'utf8'));
const manifest = JSON.parse(zlib.brotliDecompressSync(fs.readFileSync(path.join(PKG, latest.manifest))).toString());
const nChunks = Math.ceil(expected.size / manifest.chunkSize);
if (manifest.chunks.n !== nChunks) throw new Error(`manifest chunks ${manifest.chunks.n} != expected ${nChunks}`);
console.log(`asset: ${expected.path} ${(expected.size / 1e6).toFixed(1)}MB = ${nChunks} chunks, sha256 ${expected.sha256.slice(0, 16)}…`);

function run(cmd: string, args: string[]): void {
  try {
    execFileSync(cmd, args, { stdio: 'inherit' });
  } catch (e: any) {
    throw new Error(`${path.basename(cmd)} failed (exit ${e.status})`);
  }
}

// ---- 3. server + chrome ----
console.log('[3/4] e2e');
const srv = await spawnServer(PKG, { appDir: APP, latencyMs: LAT, mbps: MBPS });
fs.mkdirSync(path.join(root, 'work/chrome-profiles'), { recursive: true });
const udd = fs.mkdtempSync(path.join(root, 'work/chrome-profiles/asset-e2e-'));
const base = encodeURIComponent(srv.url + '/');

async function runChrome(scenario: string): Promise<any> {
  const url = `${srv.url}/app/index.html?scenario=${scenario}&base=${base}&chunk=${CORRUPT_CHUNK}`;
  // HTTP ディスクキャッシュだけシナリオ毎に新しくする (user-data-dir の OPFS/IDB は使い回し)。
  // immutable URL の chunk を Chrome が HTTP cache から応答すると origin 到達回数を数えられなくなるため。
  const dcd = fs.mkdtempSync(path.join(root, 'work/chrome-profiles/diskcache-'));
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

const setNet = async (on: boolean) => void (await fetch(`${srv.url}/__net?mode=${on ? 'on' : 'off'}`));
const getStats = async (): Promise<{ byKind: Record<string, number> }> => (await (await fetch(`${srv.url}/__stats`)).json()) as { byKind: Record<string, number> };

interface Scenario {
  name: string;
  net: boolean;
  check: (r: any, stats: { byKind: Record<string, number> }) => string[];
}
const scenarios: Scenario[] = [
  {
    name: 'cold',
    net: true,
    check: (r, stats) => {
      const out: string[] = [];
      if (r.pass1.source !== 'network') out.push(`source=${r.pass1.source} (want network)`);
      if (r.pass1.fromNetwork !== nChunks) out.push(`fromNetwork=${r.pass1.fromNetwork} (want ${nChunks})`);
      if ((stats.byKind.chunk ?? 0) !== nChunks) out.push(`server chunk reqs=${stats.byKind.chunk} (want ${nChunks})`);
      if (!r.shaOk) out.push('sha256 mismatch');
      if (!r.wasmValid || r.exports <= 0) out.push(`exports=${r.exports}`);
      if (!r.tiers.opfs || !r.tiers.idb) out.push(`tiers after cold: ${JSON.stringify(r.tiers)}`);
      if (!r.sizeMatches) out.push('manifest size mismatch');
      return out;
    },
  },
  {
    name: 'warm-netoff',
    net: false,
    check: (r, stats) => {
      const out: string[] = [];
      if (r.pass1.fromNetwork !== 0) out.push(`fromNetwork=${r.pass1.fromNetwork} (want 0)`);
      if ((stats.byKind.chunk ?? 0) !== 0) out.push(`server chunk reqs=${stats.byKind.chunk} (want 0)`);
      if (r.pass1.fromOpfs + r.pass1.fromIdb !== nChunks) out.push(`cache hits=${r.pass1.fromOpfs + r.pass1.fromIdb} (want ${nChunks})`);
      if (!r.shaOk) out.push('sha256 mismatch');
      if (!r.wasmValid) out.push(`exports=${r.exports}`);
      return out;
    },
  },
  {
    name: 'corrupt-opfs',
    net: false,
    check: (r, stats) => {
      const out: string[] = [];
      if (r.pass1.corruptChunks < 1) out.push(`corruptChunks=${r.pass1.corruptChunks} (want >=1)`);
      if (r.pass1.fromIdb < 1) out.push(`fromIdb=${r.pass1.fromIdb} (repair should come from IDB)`);
      if (r.pass1.fromNetwork !== 0) out.push(`fromNetwork=${r.pass1.fromNetwork} (want 0)`);
      if (!r.shaOk) out.push('sha256 mismatch');
      if (!r.wasmValid) out.push(`exports=${r.exports}`);
      return out;
    },
  },
  {
    name: 'corrupt-both',
    net: true,
    check: (r, stats) => {
      const out: string[] = [];
      if (r.pass1.corruptChunks < 2) out.push(`corruptChunks=${r.pass1.corruptChunks} (want >=2: opfs+idb)`);
      if (r.pass1.fromNetwork !== 1) out.push(`fromNetwork=${r.pass1.fromNetwork} (want 1)`);
      if ((stats.byKind.chunk ?? 0) !== 1) out.push(`server chunk reqs=${stats.byKind.chunk} (want 1)`);
      if (!r.shaOk) out.push('sha256 mismatch');
      if (!r.wasmValid) out.push(`exports=${r.exports}`);
      return out;
    },
  },
];

const results: Record<string, any> = { asset: expected, nChunks, shaping: { latencyMs: LAT, mbps: MBPS }, runs: {} };
let failed = 0;
const must = (cond: boolean, msg: string) => {
  console.log(cond ? '  ok  ' : '  FAIL', msg);
  if (!cond) failed++;
};

console.log('[4/4] scenarios');
for (const sc of scenarios) {
  console.log(`[chrome:${sc.name}] (net ${sc.net ? 'on' : 'OFF'})`);
  await srv.reset();
  await setNet(sc.net);
  let rep: any;
  try {
    rep = await runChrome(sc.name);
  } catch (e: any) {
    rep = { ok: false, error: String(e.message ?? e) };
  }
  const stats = await getStats();
  results.runs[sc.name] = rep;
  if (!rep.ok) {
    console.log('  FAIL report:', rep.error, 'stage=', rep.stage);
    failed++;
    continue;
  }
  const p = rep.res;
  console.log(`  report: compile=${p.compileMs}ms exports=${p.exports} source=${p.pass1?.source} net=${p.pass1?.fromNetwork} opfs=${p.pass1?.fromOpfs} idb=${p.pass1?.fromIdb} corrupt=${p.pass1?.corruptChunks} shaOk=${p.shaOk}`);
  const problems = sc.check(p, stats);
  must(problems.length === 0, `${sc.name}: ${problems.length ? problems.join('; ') : 'all checks'}`);
}
await setNet(true);

fs.writeFileSync(path.join(root, 'work/results-asset-e2e.json'), JSON.stringify(results, null, 1));
await srv.close();
if (!KEEP) fs.rmSync(udd, { recursive: true, force: true });
console.log(failed ? `FAILED: ${failed}` : 'ALL PASS');
process.exit(failed ? 1 : 0);
