// node 上の VFS 結合テスト + 実測 (ローカル HTTP サーバ + fetcher worker_threads + SlotCache(fs))。
//   node test/node-test.ts --pkg work/pkg-t1 [--inv work/inv_win.jsonl] [--latency 0] [--mbps 0] [--out work/results-node.json]
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { Worker } from 'node:worker_threads';
import { spawnServer } from './spawn-server.ts';
import { fetchManifest, openVfs, loadNodeDecoders, VfsError } from '../vfs/index.ts';
import type { WorkerLike } from '../vfs/index.ts';
import { openNodeSyncFile } from '../vfs/node-file.ts';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..');
const PKG = path.resolve(root, A.pkg ?? 'work/pkg-t1');
const INV = path.resolve(root, A.inv ?? 'work/inv_win.jsonl');
const OUT = path.resolve(root, A.out ?? 'work/results-node.json');
const LAT = Number(A.latency ?? 0);
const MBPS = Number(A.mbps ?? 0);
const SAMPLE = Number(A.sample ?? 400);
const ROOT_WIN = 'C:\\Program Files\\Image-Line\\FL Studio 2026';

let failed = 0;
const results: Record<string, unknown> = { pkg: PKG, shaping: { latencyMs: LAT, mbps: MBPS } };
function check(cond: boolean, msg: string) {
  console.log(cond ? '  ok  ' : '  FAIL', msg);
  if (!cond) failed++;
}
const sha = (b: Uint8Array) => crypto.createHash('sha256').update(b).digest('hex');
const pct = (a: number[], p: number) => (a.length ? [...a].sort((x, y) => x - y)[Math.min(a.length - 1, Math.floor(a.length * p))] : NaN);

const spawn = (): WorkerLike => {
  const w = new Worker(new URL('../vfs/fetch-worker.ts', import.meta.url));
  w.unref();
  return { postMessage: (m) => w.postMessage(m), terminate: () => void w.terminate(), onMessage: (cb) => void w.on('message', cb) };
};

await loadNodeDecoders();
const srv = await spawnServer(PKG, { latencyMs: LAT, mbps: MBPS });
const manifest = await fetchManifest(srv.url);
const gsz = Object.fromEntries(Object.entries(manifest.groups).map(([k, v]) => [k, v.reduce((a, x) => a + x[1], 0)]));
console.log(`manifest: ${manifest.chunks.n} chunks, groups ${JSON.stringify(gsz)}`);
await srv.reset();

interface Inv {
  p: string;
  size: number;
  disk: string;
  cat: string;
  cls: string;
}
const inv: Inv[] = fs
  .readFileSync(INV, 'utf8')
  .trim()
  .split('\n')
  .map((l) => JSON.parse(l));
const present = (p: string) => {
  let d: any = manifest.tree;
  for (const part of p.split('/')) {
    if (!d || Array.isArray(d)) return false;
    d = d[part];
  }
  return d !== undefined;
};
const expected = inv.filter((e) => e.cls !== 'skip' && present(e.p));
const dataFiles = expected.filter((e) => e.cat !== 'exec');
const stubFiles = expected.filter((e) => e.cat === 'exec');
console.log(`expected files in pkg: ${expected.length} (data ${dataFiles.length}, stub ${stubFiles.length})`);

const cacheFile = path.join(PKG, '..', 'node-cache-' + path.basename(PKG) + '.bin');
fs.rmSync(cacheFile, { force: true });
const mk = (cacheMB: number, file: string | null = cacheFile) =>
  openVfs({
    baseUrl: srv.url + '/',
    manifest,
    cacheFile: file ? openNodeSyncFile(file) : null,
    maxCacheBytes: cacheMB * 2 ** 20,
    loader: 'sab',
    spawn,
    nodeDecoders: true,
    verify: true,
    roots: [ROOT_WIN],
  });

console.log('[1] namespace');
{
  const { vfs, ready } = mk(256);
  await ready;
  let ok = 0;
  for (const e of expected) {
    const s = vfs.statSync(e.p);
    if (s && s.type === 'file' && s.size === e.size) ok++;
  }
  check(ok === expected.length, `stat size match ${ok}/${expected.length}`);
  const e0 = dataFiles[0];
  check(!!vfs.statSync(ROOT_WIN + '\\' + e0.p.replace(/\//g, '\\').toUpperCase()), 'win path + root prefix + case-insensitive');
  check(vfs.statSync('does/not/exist') === null, 'stat ENOENT -> null');
  let threw = false;
  try {
    vfs.openSync('nope');
  } catch (e) {
    threw = (e as VfsError).code === 'ENOENT';
  }
  check(threw, 'open ENOENT');
  const top = vfs.readdirSync('');
  check(top.length > 0 && top.every((x) => x.name.length > 0), 'readdir root');
  const dirs = new Set<string>();
  for (const e of expected) dirs.add(e.p.split('/').slice(0, -1).join('/'));
  let dOk = 0;
  const dl = [...dirs].slice(0, 200);
  for (const d of dl) {
    const names = new Set(vfs.readdirSync(d).map((x) => x.name));
    const pre = d ? d + '/' : '';
    const exp = expected.filter((e) => e.p.startsWith(pre) && !e.p.slice(pre.length).includes('/')).map((e) => e.p.split('/').pop()!);
    if (exp.every((n) => names.has(n))) dOk++;
  }
  check(dOk === dl.length, `readdir lists files ${dOk}/${dl.length} dirs`);
  if (stubFiles.length) {
    const sf = stubFiles[0];
    check(vfs.statSync(sf.p)!.stub === true, 'stub flag in stat');
    const fd = vfs.openSync(sf.p);
    let c = '';
    try {
      vfs.readSync(fd, new Uint8Array(16));
    } catch (e) {
      c = (e as VfsError).code;
    }
    check(c === 'ESTUB', 'stub read -> ESTUB');
  }
  vfs.close();
}

console.log('[2] content integrity');
const timings: Record<string, unknown> = {};
let pickedFiles: Inv[] = [];
{
  fs.rmSync(cacheFile, { force: true });
  const { vfs, cache, ready } = mk(256);
  await ready;
  const pick = dataFiles.length <= SAMPLE ? dataFiles : dataFiles.filter((_, i) => i % Math.ceil(dataFiles.length / SAMPLE) === 0);
  pickedFiles = pick;
  let bad = 0;
  let bytes = 0;
  const t0 = performance.now();
  for (const e of pick) {
    const got = vfs.readFileSync(e.p);
    const want = fs.readFileSync(e.disk);
    bytes += got.length;
    if (got.length !== want.length || sha(got) !== sha(want)) {
      bad++;
      console.log('  mismatch', e.p);
    }
  }
  const dt = performance.now() - t0;
  check(bad === 0, `content sha256 match ${pick.length - bad}/${pick.length} files (${(bytes / 1e6).toFixed(1)} MB, ${Math.round(dt)} ms)`);
  timings.contentCheck = { files: pick.length, bytes, ms: Math.round(dt) };
  const big = dataFiles.filter((e) => e.size > 3 * 2 ** 20).sort((a, b) => b.size - a.size)[0];
  if (big) {
    const fd = vfs.openSync(big.p);
    const want = fs.readFileSync(big.disk);
    let rbad = 0;
    const cs = manifest.chunkSize;
    const cases: [number, number][] = [[0, 1], [cs - 3, 7], [cs, 1], [2 * cs - 1, 2], [big.size - 5, 100], [big.size - 1, 1], [123456, 3 * cs + 17]];
    for (let i = 0; i < 40; i++) cases.push([Math.floor(Math.random() * big.size), Math.floor(Math.random() * 200000) + 1]);
    for (const [pos, len] of cases) {
      const b = new Uint8Array(len);
      const n = vfs.readSync(fd, b, 0, len, pos);
      const exp = Math.max(0, Math.min(len, big.size - pos));
      if (n !== exp || sha(b.subarray(0, n)) !== sha(want.subarray(pos, pos + n))) {
        rbad++;
        console.log('  range mismatch', pos, len, n, exp);
      }
    }
    vfs.seekSync(fd, 0);
    const seqBuf = new Uint8Array(65536);
    let off = 0;
    let sbad = 0;
    for (let i = 0; i < 20; i++) {
      const n = vfs.readSync(fd, seqBuf);
      if (sha(seqBuf.subarray(0, n)) !== sha(want.subarray(off, off + n))) sbad++;
      off += n;
    }
    check(rbad === 0 && sbad === 0, `range/sequential reads on ${big.p} (${(big.size / 1e6).toFixed(1)} MB): ${cases.length} ranges + 20 seq`);
  }
  results.cacheAfterContent = cache.stats;
  vfs.close();
}

console.log('[3] persistent cache (restart)');
{
  const { vfs, cache, ready } = mk(256);
  await ready;
  await srv.reset();
  const sample = pickedFiles;
  let bad = 0;
  for (const e of sample) if (sha(vfs.readFileSync(e.p)) !== sha(fs.readFileSync(e.disk))) bad++;
  const net = await srv.stats();
  check(bad === 0, 'warm content match');
  check(net.byKind.chunk === undefined, `restart: chunk requests = ${net.byKind.chunk ?? 0} (expect 0), scanned slots ${(cache as any).scanned}`);
  results.warmRestart = { files: sample.length, chunkRequests: net.byKind.chunk ?? 0, cacheSlotsScanned: (cache as any).scanned };
  vfs.close();
}

console.log('[4] eviction + pin');
{
  const small = 8;
  const { vfs, cache, ready } = mk(small, cacheFile + '.small');
  await ready;
  const group = Object.keys(manifest.groups)[0];
  const pins = vfs.index.groupChunks(group).slice(0, 2);
  await vfs.preload(pins, { pin: true });
  const files = dataFiles.filter((_, i) => i % 7 === 0).slice(0, 120);
  let bad = 0;
  for (const e of files) if (sha(vfs.readFileSync(e.p)) !== sha(fs.readFileSync(e.disk))) bad++;
  check(bad === 0, 'content ok under eviction pressure');
  check(cache.stats.evictions > 0, `evictions occurred (${cache.stats.evictions}, slots ${cache.stats.slots}, used ${cache.stats.used})`);
  check(pins.every((c) => cache.has(vfs.index.chunkId(c))), 'pinned chunks survive eviction');
  results.eviction = { maxMiB: small, evictions: cache.stats.evictions, used: cache.stats.used, slots: cache.stats.slots };
  vfs.close();
  fs.rmSync(cacheFile + '.small', { force: true });
}

console.log('[5] measurements (cold)');
{
  fs.rmSync(cacheFile, { force: true });
  const { vfs, cache, loader, ready } = mk(1024);
  await ready;
  const smalls = dataFiles.filter((e) => e.size > 0 && e.size <= manifest.smallMax);
  let s = 12345;
  const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const smp = [...smalls].sort(() => rnd() - 0.5).slice(0, 120);
  const lat: number[] = [];
  for (const e of smp) {
    const t = performance.now();
    vfs.readFileSync(e.p);
    lat.push(performance.now() - t);
  }
  const wlat: number[] = [];
  for (const e of smp) {
    const t = performance.now();
    vfs.readFileSync(e.p);
    wlat.push(performance.now() - t);
  }
  results.smallFirstRead = {
    n: smp.length,
    coldMs: { p50: pct(lat, 0.5), p95: pct(lat, 0.95), min: Math.min(...lat), max: Math.max(...lat) },
    warmMs: { p50: pct(wlat, 0.5), p95: pct(wlat, 0.95) },
    missLatencyMs: { p50: pct(vfs.missLatencies, 0.5), p95: pct(vfs.missLatencies, 0.95), n: vfs.missLatencies.length },
  };
  const bigs = dataFiles.filter((e) => e.size > 8 * 2 ** 20).sort((a, b) => b.size - a.size).slice(0, 3);
  const seqRes: any[] = [];
  for (const e of bigs) {
    const fd = vfs.openSync(e.p);
    const buf = new Uint8Array(256 * 1024);
    let pos = 0;
    let firstMs = 0;
    const t0 = performance.now();
    while (pos < e.size) {
      const n = vfs.readSync(fd, buf, 0, buf.length, pos);
      if (pos === 0) firstMs = performance.now() - t0;
      pos += n;
    }
    const dt = performance.now() - t0;
    vfs.closeSync(fd);
    vfs.clearMemory();
    const fd2 = vfs.openSync(e.p);
    const t1 = performance.now();
    pos = 0;
    while (pos < e.size) pos += vfs.readSync(fd2, buf, 0, buf.length, pos);
    const dt2 = performance.now() - t1;
    vfs.closeSync(fd2);
    seqRes.push({ file: e.p, MB: +(e.size / 1e6).toFixed(1), coldMBps: +(e.size / 1e6 / (dt / 1000)).toFixed(1), coldFirstReadMs: +firstMs.toFixed(1), warmMBps: +(e.size / 1e6 / (dt2 / 1000)).toFixed(1) });
  }
  results.sequential = seqRes;
  results.vfsStats = { ...vfs.stats, evictions: cache.stats.evictions };
  results.fetcher = await loader.stat();
  check((results.fetcher as { maxInflight: number }).maxInflight > 1, `readahead issues parallel fetches (fetcher maxInflight=${(results.fetcher as { maxInflight: number }).maxInflight})`);
  const ds = vfs.debugState();
  check(ds.memChunks <= ds.memLimit && ds.maxReadahead === 8, `defaults applied (memChunks ${ds.memChunks}/${ds.memLimit}, maxReadahead ${ds.maxReadahead})`);
  console.log(JSON.stringify({ smallFirstRead: results.smallFirstRead, sequential: seqRes, fetcher: results.fetcher }, null, 1));
  vfs.close();
}

console.log('[6] preload boot groups');
{
  fs.rmSync(cacheFile, { force: true });
  const { vfs, ready } = mk(1024);
  await ready;
  await srv.reset();
  const groups: Record<string, unknown> = {};
  for (const g of ['T0', 'T0p']) {
    if (!manifest.groups[g]) continue;
    const r = await vfs.preload(g, { concurrency: 8, pin: true });
    groups[g] = { ...r, ms: Math.round(r.ms) };
  }
  results.preloadBoot = groups;
  results.preloadNet = await srv.stats();
  console.log('preload', JSON.stringify(groups), JSON.stringify(results.preloadNet));
  vfs.close();
}

results.failed = failed;
results.timings = timings;
fs.writeFileSync(OUT, JSON.stringify(results, null, 1));
await srv.close();
fs.rmSync(cacheFile, { force: true });
console.log(failed ? `FAILED: ${failed}` : 'ALL PASS');
process.exit(failed ? 1 : 0);
