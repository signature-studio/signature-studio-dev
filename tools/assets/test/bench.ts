// ネットワーク整形下 (遅延/帯域) の readahead・preload 並列度・小ファイル初回レイテンシの実測 (node + 実パッケージ)。
//   node test/bench.ts --pkg work/pkg-full [--out work/bench-net.json]
import fs from 'node:fs';
import path from 'node:path';
import { Worker } from 'node:worker_threads';
import { spawnServer } from './spawn-server.ts';
import { fetchManifest, openVfs, loadNodeDecoders } from '../vfs/index.ts';
import type { WorkerLike } from '../vfs/index.ts';
import { openNodeSyncFile } from '../vfs/node-file.ts';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..');
const PKG = path.resolve(root, A.pkg ?? 'work/pkg-full');
const OUT = path.resolve(root, A.out ?? 'work/bench-net.json');
const spawn = (): WorkerLike => {
  const w = new Worker(new URL('../vfs/fetch-worker.ts', import.meta.url));
  w.unref();
  return { postMessage: (m) => w.postMessage(m), terminate: () => void w.terminate(), onMessage: (cb) => void w.on('message', cb) };
};
const pct = (a: number[], p: number) => (a.length ? [...a].sort((x, y) => x - y)[Math.min(a.length - 1, Math.floor(a.length * p))] : NaN);

await loadNodeDecoders();
const srv = await spawnServer(PKG);
const manifest = await fetchManifest(srv.url);
const cacheFile = path.join(PKG, '..', 'bench-cache.bin');

// 対象ファイル: 大きい無圧縮(wv/flac/ogg 等)と圧縮可能(.flexpack 等), 小ファイル群
const inv = fs.readFileSync(path.join(root, 'work/inv_win.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
const present = (p: string) => {
  let d: any = manifest.tree;
  for (const part of p.split('/')) {
    if (!d || Array.isArray(d)) return false;
    d = d[part];
  }
  return d !== undefined;
};
const files = inv.filter((e: any) => e.cat !== 'exec' && e.cls !== 'skip' && e.size > 0 && present(e.p));
const bigFile = files.filter((e: any) => e.size > 30e6 && e.size < 50e6 && /flexpack$/i.test(e.p)).sort((a: any, b: any) => b.size - a.size)[0] ?? files.sort((a: any, b: any) => b.size - a.size)[0];
const wavBig = files.filter((e: any) => /\.wav$/i.test(e.p) && e.size > 8e6).sort((a: any, b: any) => b.size - a.size)[0];
const smalls = files.filter((e: any) => e.size <= manifest.smallMax);
let s = 777;
const rnd = () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;

const scenarios: [string, number, number][] = [
  ['localhost (unshaped)', 0, 0],
  ['broadband 40ms/200Mbps', 40, 200],
  ['slow 100ms/50Mbps', 100, 50],
];
const out: any = { pkg: PKG, bigFile: bigFile.p, bigMB: bigFile.size / 1e6, wavBig: wavBig?.p, scenarios: [] };

async function fresh(opts: { readahead: number; slots?: number }) {
  fs.rmSync(cacheFile, { force: true });
  const o = openVfs({ baseUrl: srv.url + '/', manifest, cacheFile: openNodeSyncFile(cacheFile), maxCacheBytes: 2 ** 30, loader: 'sab', spawn, nodeDecoders: true, verify: false, maxReadahead: opts.readahead, nSlots: opts.slots ?? 16 });
  await o.ready;
  return o;
}

for (const [name, lat, mbps] of scenarios) {
  await srv.shape(lat, mbps);
  const sc: any = { name, latencyMs: lat, mbps, sequential: [], smallCold: {}, preload: [] };
  for (const [label, f] of [['flexpack(br)', bigFile], ['wav(raw/br)', wavBig]] as const) {
    if (!f) continue;
    for (const ra of [0, 2, 8, 16]) {
      const o = await fresh({ readahead: ra });
      const fd = o.vfs.openSync(f.p);
      const buf = new Uint8Array(256 * 1024);
      let pos = 0;
      let first = 0;
      const t0 = performance.now();
      while (pos < f.size) {
        const n = o.vfs.readSync(fd, buf, 0, buf.length, pos);
        if (pos === 0) first = performance.now() - t0;
        pos += n;
      }
      const dt = performance.now() - t0;
      sc.sequential.push({ file: label, MB: +(f.size / 1e6).toFixed(1), readahead: ra, firstReadMs: +first.toFixed(1), totalMs: Math.round(dt), MBps: +(f.size / 1e6 / (dt / 1000)).toFixed(1) });
      o.vfs.close();
    }
  }
  // 小ファイル (pack) 初回: 120 ランダム
  {
    const o = await fresh({ readahead: 8 });
    const smp = [...smalls].sort(() => rnd() - 0.5).slice(0, 60);
    const lats: number[] = [];
    for (const e of smp) {
      const t = performance.now();
      o.vfs.readFileSync(e.p);
      lats.push(performance.now() - t);
    }
    const miss = o.vfs.missLatencies;
    sc.smallCold = { n: smp.length, firstAccessMs: { p50: +pct(lats, 0.5).toFixed(2), p95: +pct(lats, 0.95).toFixed(2) }, missMs: { n: miss.length, p50: +pct(miss, 0.5).toFixed(1), p95: +pct(miss, 0.95).toFixed(1) } };
    o.vfs.close();
  }
  // preload T0+T0p 並列度
  for (const conc of [1, 4, 8, 16]) {
    const o = await fresh({ readahead: 8 });
    const t0 = performance.now();
    let bytes = 0;
    let chunks = 0;
    for (const g of ['T0', 'T0p']) {
      const r = await o.vfs.preload(g, { concurrency: conc });
      bytes += r.bytes;
      chunks += r.fetched;
    }
    sc.preload.push({ concurrency: conc, chunks, MB: +(bytes / 1e6).toFixed(2), ms: Math.round(performance.now() - t0) });
    o.vfs.close();
  }
  console.log(JSON.stringify(sc));
  out.scenarios.push(sc);
}
fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
fs.rmSync(cacheFile, { force: true });
await srv.close();
process.exit(0);
