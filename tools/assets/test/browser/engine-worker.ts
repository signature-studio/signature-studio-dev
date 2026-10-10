// エンジン Worker 役: OPFS SyncAccessHandle キャッシュ + SAB 同期ローダで LazyVfs を動かし、実測値を返す。
import { fetchManifest, openVfs, VfsError } from '../../vfs/index.ts';
import type { WorkerLike } from '../../vfs/index.ts';
import { openOpfsSyncFile, removeOpfsFile } from '../../vfs/opfs.ts';

interface Exp {
  p: string;
  size: number;
  sha: string;
}
const g = self as any;
const hex = (b: ArrayBuffer) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');
const sha256 = async (b: Uint8Array) => hex(await crypto.subtle.digest('SHA-256', b as BufferSource));
const pct = (a: number[], p: number) => (a.length ? [...a].sort((x, y) => x - y)[Math.min(a.length - 1, Math.floor(a.length * p))] : NaN);

/** 各段階の進行を main へ通知 (停止時の足跡)。監視タイマも main 側に置く。 */
export type Progress = (stage: string) => void;
const withTimeout = <T>(p: Promise<T>, ms: number, what: string): Promise<T> =>
  new Promise<T>((res, rej) => {
    const t = setTimeout(() => rej(new Error(`timeout ${ms}ms: ${what}`)), ms);
    p.then((v) => { clearTimeout(t); res(v); }, (e) => { clearTimeout(t); rej(e); });
  });

g.onmessage = async (e: MessageEvent) => {
  const t0 = Date.now();
  let stage = 'boot';
  const progress: Progress = (s) => {
    stage = s;
    g.postMessage({ ok: 'progress', stage, elapsedMs: Date.now() - t0 });
  };
  try {
    const res = await run(e.data, progress);
    g.postMessage({ ok: true, res });
  } catch (err) {
    g.postMessage({ ok: false, error: String((err as Error).stack ?? err), stage, elapsedMs: Date.now() - t0 });
  }
};

async function run(cfg: { base: string; phase: string; loader: 'sab' | 'xhr'; expected: { files: Exp[]; big: Exp[]; boot: boolean }; pageIsolated: boolean; verify: boolean; ra: number }, progress: Progress) {
  const r: Record<string, any> = { phase: cfg.phase, loader: cfg.loader, workerIsolated: g.crossOriginIsolated, pageIsolated: cfg.pageIsolated, sab: typeof SharedArrayBuffer !== 'undefined', ua: navigator.userAgent };
  progress('manifest');
  const manifest = await fetchManifest(cfg.base);
  const slotName = `slots-${manifest.chunkSize}.bin`;
  const cold = cfg.phase.includes('cold');
  if (cold) await removeOpfsFile(slotName);
  progress('opfs-open');
  const t0 = performance.now();
  const file = await withTimeout(openOpfsSyncFile(slotName), 30000, 'openOpfsSyncFile');
  r.opfsOpened = !!file;
  r.openMs = +(performance.now() - t0).toFixed(1);

  // 別 Worker から同一ファイルを開こうとして排他 (別タブ相当) を確認
  if (file && cold) {
    progress('probe-open');
    const probe = new Worker(new URL('./probe-worker.js', import.meta.url), { type: 'module' });
    r.secondHandleBlocked = await withTimeout(
      new Promise<boolean>((res, rej) => {
        probe.onerror = (e) => rej(new Error('probe-worker error: ' + (e as ErrorEvent).message));
        probe.onmessage = (m) => res(m.data === null);
        probe.postMessage(slotName);
      }),
      30000,
      'probe-worker reply'
    );
    probe.terminate();
  }

  const spawn = (): WorkerLike => {
    const w = new Worker(new URL('./fetch-worker.js', import.meta.url), { type: 'module' });
    return { postMessage: (m) => w.postMessage(m), terminate: () => void w.terminate(), onMessage: (cb) => void (w.onmessage = (ev) => cb(ev.data)) };
  };
  progress('loader-init');
  const { vfs, cache, loader, ready } = openVfs({ baseUrl: cfg.base, manifest, cacheFile: file, maxCacheBytes: 1024 * 2 ** 20, loader: cfg.loader, spawn, verify: cfg.verify, maxReadahead: cfg.ra });
  await withTimeout(ready, 60000, 'fetcher ready (nested worker)'); // nested Worker は親が空いていないと起動できない
  progress('stat');
  r.cacheKind = cache.stats.kind;
  r.cacheScannedSlots = (cache as any).scanned ?? 0;

  // 1. namespace
  let sizeOk = 0;
  for (const e of cfg.expected.files) if (vfs.statSync(e.p)?.size === e.size) sizeOk++;
  r.statOk = `${sizeOk}/${cfg.expected.files.length}`;

  // 2. content (sha256) + wall
  const tc = performance.now();
  let bad = 0;
  let bytes = 0;
  const lat: number[] = [];
  for (const e of cfg.expected.files) {
    const t = performance.now();
    const d = vfs.readFileSync(e.p);
    lat.push(performance.now() - t);
    bytes += d.length;
    if ((await sha256(d)) !== e.sha) bad++;
  }
  r.content = { files: cfg.expected.files.length, mismatches: bad, MB: +(bytes / 1e6).toFixed(1), ms: Math.round(performance.now() - tc), readMs: { p50: +pct(lat, 0.5).toFixed(3), p95: +pct(lat, 0.95).toFixed(3), max: +Math.max(...lat).toFixed(2) } };
  r.missLatencyMs = { n: vfs.missLatencies.length, p50: +pct(vfs.missLatencies, 0.5).toFixed(2), p95: +pct(vfs.missLatencies, 0.95).toFixed(2) };

  // 3. 大ファイル逐次
  r.sequential = [];
  for (const e of cfg.expected.big) {
    const fd = vfs.openSync(e.p);
    const buf = new Uint8Array(256 * 1024);
    const run1 = () => {
      let pos = 0;
      let first = 0;
      const t = performance.now();
      while (pos < e.size) {
        const n = vfs.readSync(fd, buf, 0, buf.length, pos);
        if (pos === 0) first = performance.now() - t;
        pos += n;
      }
      return { ms: performance.now() - t, first };
    };
    const a = run1();
    vfs.clearMemory();
    const b = run1();
    vfs.closeSync(fd);
    r.sequential.push({ file: e.p, MB: +(e.size / 1e6).toFixed(1), firstReadMs: +a.first.toFixed(1), coldMBps: +(e.size / 1e6 / (a.ms / 1000)).toFixed(1), warmMBps: +(e.size / 1e6 / (b.ms / 1000)).toFixed(1) });
  }

  // 4. ブートセット preload (async 経路) — cold のみ意味あり
  if (cfg.expected.boot && cfg.phase === 'cold') {
    const out: Record<string, unknown> = {};
    for (const gname of ['T0', 'T0p']) {
      if (!manifest.groups[gname]) continue;
      // 別キャッシュ状態を作らないため、未取得 chunk だけ取る
      const p = await vfs.preload(gname, { concurrency: 8, pin: true });
      out[gname] = { ...p, ms: Math.round(p.ms) };
    }
    r.preloadBoot = out;
  }

  // 5. stub / ENOENT
  let c = '';
  try {
    vfs.openSync('no/such');
  } catch (err) {
    c = (err as VfsError).code;
  }
  r.enoent = c;

  r.vfsStats = { ...vfs.stats, evictions: cache.stats.evictions, cacheUsed: cache.stats.used };
  r.fetcher = await loader.stat();
  cache.flush();
  vfs.close();
  return r;
}
