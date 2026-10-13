// Serum 2 コンテンツ配信 e2e (#70): pack 済み pkg を HTTP 配信し LazyVfs (SAB loader) 経由で全ファイルを読む。
//   node serum2/serum2-e2e.ts --pkg <pkg> --src <extracted-root> --ref <ref-flac.json> --wasm <flacdec.wasm>
//        [--mode pass|neg-chunk|neg-flac|neg-ref] [--out result.json]
// 検査 (1 つでも不合格なら exit 1。件数は failures に数える):
//   [1] manifest tree と src の突合 (7,357 files / 1,392,825,417 B)
//   [2] Tables 全件 (289 files) 読み + 再起動 warm (chunk request 0)
//   [3] 全 7,357 files を VFS から読み sha256 を src と照合
//   [4] 全 4,747 FLAC を wasm libFLAC 1.5.0 で復号 (MD5 検証込み) し PCM sha256 を libsndfile 参照と照合
//   [5] HTTP Range: raw chunk への Range GET (206) と、VFS のランダム範囲読み
// --mode neg-*: 1 件だけ壊して不合格になることを確認するためのネガティブコントロール (wrapper が exit 1 + failures=1 を要求)
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { Worker } from 'node:worker_threads';
import { spawnServer } from '../test/spawn-server.ts';
import { fetchManifest, openVfs, loadNodeDecoders } from '../vfs/index.ts';
import type { WorkerLike, Manifest } from '../vfs/index.ts';
import { openNodeSyncFile } from '../vfs/node-file.ts';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
for (const k of ['pkg', 'src', 'ref', 'wasm']) if (!A[k]) throw new Error(`--${k} required`);
const MODE = A.mode ?? 'pass';
const SRC = path.resolve(A.src);
let PKG = path.resolve(A.pkg);
const TMP = process.env.TMPDIR ?? os.tmpdir();
const WORK = fs.mkdtempSync(path.join(TMP, 'serum2-e2e-'));

let failures = 0;
const fail = (msg: string) => {
  failures++;
  console.log('  FAIL', msg);
};
const check = (cond: boolean, msg: string) => {
  if (cond) console.log('  ok  ', msg);
  else fail(msg);
};
const sha = (b: Uint8Array) => crypto.createHash('sha256').update(b).digest('hex');
const result: Record<string, unknown> = { mode: MODE, node: process.version, nproc: os.cpus().length, load1: os.loadavg()[0] };
const T0 = performance.now();
const lap = (k: string, t: number) => (result[k] = Math.round((performance.now() - t) * 10) / 10);

// ---- ground truth: src ディレクトリ (pack 対象 = content のみ) ----
interface Ent {
  p: string;
  size: number;
  sha: string;
}
const truth: Ent[] = [];
{
  const t = performance.now();
  (function walk(d: string, rel: string) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (!rel && (e.name === '$COMMONFILES64' || e.name === '$PLUGINSDIR')) continue;
      const r = rel ? rel + '/' + e.name : e.name;
      if (e.isDirectory()) walk(path.join(d, e.name), r);
      else truth.push({ p: r, size: fs.statSync(path.join(d, e.name)).size, sha: '' });
    }
  })(SRC, '');
  truth.sort((a, b) => (a.p < b.p ? -1 : 1));
  for (const e of truth) e.sha = sha(fs.readFileSync(path.join(SRC, e.p)));
  lap('truthMs', t);
}
const refFlac: Record<string, { sha: string; ch: number; rate: number; frames: number; bps: number }> = JSON.parse(fs.readFileSync(A.ref, 'utf8'));

// ---- neg-chunk: 1 chunk object の 1 byte を反転した pkg ビューを作る (原本は不変) ----
let negChunkTarget = '';
if (MODE === 'neg-chunk') {
  const view = path.join(WORK, 'pkg-view');
  fs.mkdirSync(path.join(view, 'c'), { recursive: true });
  for (const f of ['latest.json']) fs.symlinkSync(path.join(PKG, f), path.join(view, f));
  fs.symlinkSync(path.join(PKG, 'm'), path.join(view, 'm'));
  for (const pre of fs.readdirSync(path.join(PKG, 'c'))) {
    fs.mkdirSync(path.join(view, 'c', pre));
    for (const f of fs.readdirSync(path.join(PKG, 'c', pre))) fs.symlinkSync(path.join(PKG, 'c', pre, f), path.join(view, 'c', pre, f));
  }
  PKG = view;
}

const spawn = (): WorkerLike => {
  const w = new Worker(new URL('../vfs/fetch-worker.ts', import.meta.url));
  w.unref();
  return { postMessage: (m) => w.postMessage(m), terminate: () => void w.terminate(), onMessage: (cb) => void w.on('message', cb) };
};
await loadNodeDecoders();
const srv0 = await spawnServer(PKG);
// 長い同期ループ中に keep-alive ソケットがサーバ側で閉じるため、stats は毎回新規接続で取る
const srv = {
  ...srv0,
  stats: async () => (await (await fetch(srv0.url + '/__stats', { headers: { connection: 'close' } })).json()) as { requests: number; bytes: number; byKind: Record<string, number> },
  reset: async () => void (await (await fetch(srv0.url + '/__reset', { headers: { connection: 'close' } })).text()),
};
const die = (e: unknown) => {
  console.error('FATAL', e);
  srv0.close();
  process.exit(2);
};
process.on('uncaughtException', die);
process.on('unhandledRejection', die);
const manifest: Manifest = await fetchManifest(srv.url);
const cacheFile = path.join(WORK, 'cache.bin');
const mk = (cacheMB: number) =>
  openVfs({ baseUrl: srv.url + '/', manifest, cacheFile: openNodeSyncFile(cacheFile), maxCacheBytes: cacheMB * 2 ** 20, loader: 'sab', spawn, nodeDecoders: true, verify: true });

function leaf(p: string): [number, number?, number?, number?] | null {
  let d: any = manifest.tree;
  for (const part of p.split('/')) {
    if (!d || Array.isArray(d)) return null;
    d = d[part];
  }
  return Array.isArray(d) ? (d as any) : null;
}

if (MODE === 'neg-chunk') {
  // 最大の FLAC の先頭 chunk (専用 chunk 連続配置) の格納物を 1 byte 反転する
  const big = truth.filter((e) => e.p.endsWith('.flac') && (leaf(e.p)?.[2] ?? 0) === -1).sort((a, b) => b.size - a.size)[0];
  const first = leaf(big.p)![1]!;
  const id = manifest.chunks.id.substr(first * 32, 32);
  const ext = ['raw', 'br', 'zst'][manifest.chunks.k[first]];
  negChunkTarget = path.join(PKG, 'c', id.slice(0, 2), `${id}.${ext}`);
  const b = Buffer.from(fs.readFileSync(fs.realpathSync(negChunkTarget)));
  b[Math.min(b.length - 1, 1000)] ^= 0xff;
  fs.rmSync(negChunkTarget);
  fs.writeFileSync(negChunkTarget, b);
  result.negChunk = { file: big.p, chunk: first, codec: ext };
  console.log(`[neg-chunk] ${big.p} chunk#${first} (${ext}) を 1 byte 反転`);
}

// ---- [1] manifest tree vs truth ----
console.log('[1] manifest tree vs src');
{
  let ok = 0;
  let bytes = 0;
  const vfs0 = mk(64);
  await vfs0.ready;
  for (const e of truth) {
    const s = vfs0.vfs.statSync(e.p);
    if (s && s.type === 'file' && s.size === e.size) {
      ok++;
      bytes += s.size;
    } else fail('stat mismatch ' + e.p);
  }
  check(ok === truth.length && bytes === truth.reduce((a, e) => a + e.size, 0), `stat size match ${ok}/${truth.length} files, ${bytes} B`);
  result.files = truth.length;
  result.bytes = bytes;
  vfs0.vfs.close();
}

// ---- [2] Tables 全件 + warm restart ----
console.log('[2] Tables (wavetable) + warm restart');
{
  const tables = truth.filter((e) => e.p.startsWith('Tables/'));
  fs.rmSync(cacheFile, { force: true });
  await srv.reset();
  let { vfs, ready } = mk(1024);
  await ready;
  const t = performance.now();
  let bad = 0;
  let bytes = 0;
  for (const e of tables) {
    const got = vfs.readFileSync(e.p);
    bytes += got.length;
    if (sha(got) !== e.sha) bad++;
  }
  lap('tablesColdMs', t);
  const cold = await srv.stats();
  check(bad === 0, `Tables cold: sha256 match ${tables.length - bad}/${tables.length} files (${bytes} B), chunk requests ${cold.byKind.chunk ?? 0}`);
  vfs.close();
  ({ vfs, ready } = mk(1024));
  await ready;
  await srv.reset();
  const t2 = performance.now();
  bad = 0;
  for (const e of tables) if (sha(vfs.readFileSync(e.p)) !== e.sha) bad++;
  lap('tablesWarmMs', t2);
  const warm = await srv.stats();
  check(bad === 0 && (warm.byKind.chunk ?? 0) === 0, `Tables warm restart: sha256 match ${tables.length - bad}/${tables.length}, chunk requests ${warm.byKind.chunk ?? 0} (期待 0)`);
  result.tables = { files: tables.length, bytes, coldChunkRequests: cold.byKind.chunk ?? 0, warmChunkRequests: warm.byKind.chunk ?? 0 };
  vfs.close();
}

// ---- wasm libFLAC ----
const wasmBytes = fs.readFileSync(A.wasm);
const wmod = await WebAssembly.compile(wasmBytes);
const imports: Record<string, Record<string, unknown>> = {};
for (const i of WebAssembly.Module.imports(wmod)) (imports[i.module] ??= {})[i.name] = () => 0;
const wi = await WebAssembly.instantiate(wmod, imports as any);
const X = wi.exports as any;
if (X._initialize) X._initialize();
function wasmDecode(buf: Uint8Array) {
  const p = X.malloc(buf.length);
  new Uint8Array(X.memory.buffer, p, buf.length).set(buf);
  const rc: number = X.fd_decode(p, buf.length);
  X.free(p);
  if (rc !== 0) return { rc } as const;
  const bps: number = X.fd_bps();
  const n: number = X.fd_pcm_samples();
  const ch: number = X.fd_channels();
  const pcm = new Int32Array(X.memory.buffer, X.fd_pcm(), n);
  const lj = new Int32Array(n);
  const sh = 32 - bps;
  for (let i = 0; i < n; i++) lj[i] = pcm[i] << sh;
  const total = X.fd_total_lo() + X.fd_total_hi() * 2 ** 32;
  return { rc, ch, bps, rate: X.fd_rate() as number, frames: n / ch, total, hasMd5: !!X.fd_has_md5(), sha: sha(new Uint8Array(lj.buffer)) } as const;
}

// ---- [3]+[4] 全 files を VFS から読み sha256 照合 / FLAC を wasm 復号 ----
console.log('[3] 全ファイル VFS 読み + sha256   [4] 全 FLAC wasm 復号 (MD5 検証込み)');
const negFlac = MODE === 'neg-flac' ? truth.find((e) => e.p.endsWith('.flac') && e.size > 20000)!.p : '';
const negRef = MODE === 'neg-ref' ? truth.filter((e) => e.p.endsWith('.flac'))[7].p : '';
{
  fs.rmSync(cacheFile, { force: true });
  await srv.reset();
  const { vfs, ready, cache } = mk(1024);
  await ready;
  let shaBad = 0;
  let readErr = 0;
  let nFlac = 0;
  let flacOk = 0;
  let md5Files = 0;
  const rcCount: Record<number, number> = {};
  const bpsCount: Record<number, number> = {};
  let pcmBytes = 0;
  let readMs = 0;
  let decMs = 0;
  const t = performance.now();
  for (const e of truth) {
    let got: Uint8Array;
    const r0 = performance.now();
    try {
      got = vfs.readFileSync(e.p);
    } catch (err) {
      readErr++;
      fail(`read error ${e.p}: ${(err as Error).message}`);
      continue;
    }
    readMs += performance.now() - r0;
    if (got.length !== e.size || sha(got) !== e.sha) {
      shaBad++;
      fail('sha256 mismatch ' + e.p);
    }
    if (!e.p.endsWith('.flac')) continue;
    nFlac++;
    let input = got;
    if (e.p === negFlac) {
      input = Uint8Array.from(got);
      input[Math.floor(input.length / 2)] ^= 0x55;
    }
    const d0 = performance.now();
    const d = wasmDecode(input);
    decMs += performance.now() - d0;
    rcCount[d.rc] = (rcCount[d.rc] ?? 0) + 1;
    if (d.rc !== 0) {
      fail(`flac decode rc=${d.rc} ${e.p}`);
      continue;
    }
    bpsCount[d.bps] = (bpsCount[d.bps] ?? 0) + 1;
    if (d.hasMd5) md5Files++;
    pcmBytes += d.frames * d.ch * 4;
    const ref = refFlac[e.p];
    const refSha = e.p === negRef ? ref.sha.replace(/^./, (c) => (c === '0' ? '1' : '0')) : ref.sha;
    if (d.sha === refSha && d.ch === ref.ch && d.rate === ref.rate && d.frames === ref.frames && d.bps === ref.bps && d.frames === d.total) flacOk++;
    else fail(`flac PCM != libsndfile 参照 ${e.p} (ch ${d.ch}/${ref.ch} rate ${d.rate}/${ref.rate} frames ${d.frames}/${ref.frames} sha ${d.sha === refSha})`);
  }
  lap('fullReadDecodeMs', t);
  result.vfsReadMs = Math.round(readMs);
  result.flacDecodeMs = Math.round(decMs);
  const net = await srv.stats();
  check(shaBad === 0 && readErr === 0, `VFS read sha256 match ${truth.length - shaBad - readErr}/${truth.length} files (read errors ${readErr})`);
  check(nFlac === Object.keys(refFlac).length, `FLAC files ${nFlac} == 参照数 ${Object.keys(refFlac).length}`);
  check(flacOk === nFlac, `wasm libFLAC PCM == libsndfile PCM ${flacOk}/${nFlac} (rc 分布 ${JSON.stringify(rcCount)}, bps 分布 ${JSON.stringify(bpsCount)}, STREAMINFO MD5 有り ${md5Files})`);
  result.flac = { files: nFlac, ok: flacOk, md5Files, rcCount, bpsCount, pcmBytes };
  result.net = net;
  result.cache = (cache as any).stats;
  vfs.close();
}

// ---- [5] HTTP Range / VFS ランダム範囲 ----
console.log('[5] HTTP Range + VFS random range');
{
  const k = manifest.chunks.k;
  const nRaw = k.filter((x) => x === 0).length;
  const rawB = manifest.chunks.c.reduce((a, c, i) => a + (k[i] === 0 ? c : 0), 0);
  result.chunkCodec = { total: manifest.chunks.n, raw: nRaw, br: k.filter((x) => x === 1).length, zst: k.filter((x) => x === 2).length, rawStoredBytes: rawB };
  // raw 格納の FLAC 専用 chunk に Range GET
  const big = truth.filter((e) => e.p.endsWith('.flac') && leaf(e.p)?.[2] === -1 && k[leaf(e.p)![1]!] === 0).sort((a, b) => b.size - a.size)[0];
  const first = leaf(big.p)![1]!;
  const id = manifest.chunks.id.substr(first * 32, 32);
  const url = `${srv.url}/c/${id.slice(0, 2)}/${id}.raw`;
  const src = fs.readFileSync(path.join(SRC, big.p));
  let rangeOk = 0;
  const cases: [number, number][] = [[0, 3], [100, 199], [4096, 8191], [Math.min(manifest.chunkSize, big.size) - 10, Math.min(manifest.chunkSize, big.size) - 1]];
  for (const [a, b] of cases) {
    const res = await fetch(url, { headers: { Range: `bytes=${a}-${b}` } });
    const body = new Uint8Array(await res.arrayBuffer());
    if (res.status === 206 && body.length === b - a + 1 && sha(body) === sha(src.subarray(a, b + 1)) && res.headers.get('content-range')?.startsWith(`bytes ${a}-${b}/`)) rangeOk++;
  }
  check(rangeOk === cases.length, `raw chunk Range GET 206 + bytes 一致 ${rangeOk}/${cases.length} (${big.p}, chunk#${first})`);
  const full = await fetch(url);
  check(full.status === 200 && full.headers.get('accept-ranges') === 'bytes', 'raw chunk: 200 + Accept-Ranges: bytes');
  // br 格納 chunk は Range 不可 (Content-Encoding 付き = 仕様) を実測で確認する
  const bi = k.findIndex((x) => x === 1);
  if (bi >= 0) {
    const bid = manifest.chunks.id.substr(bi * 32, 32);
    const br = await fetch(`${srv.url}/c/${bid.slice(0, 2)}/${bid}.br`, { headers: { Range: 'bytes=0-9' } });
    await br.arrayBuffer();
    check(br.headers.get('accept-ranges') === 'none', `br chunk: Accept-Ranges none (status ${br.status}; Range は raw 格納のみ)`);
  }
  // VFS ランダム範囲 (ファイル跨ぎ・chunk 跨ぎ)
  fs.rmSync(cacheFile, { force: true });
  const { vfs, ready } = mk(256);
  await ready;
  const fd = vfs.openSync(big.p);
  let rb = 0;
  const rng = (() => {
    let s = 12345;
    return () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  })();
  const rc: [number, number][] = [[0, 1], [manifest.chunkSize - 3, 7], [manifest.chunkSize, 1], [big.size - 5, 100], [big.size - 1, 1]];
  for (let i = 0; i < 40; i++) rc.push([Math.floor(rng() * big.size), Math.floor(rng() * 200000) + 1]);
  for (const [pos, len] of rc) {
    const b = new Uint8Array(len);
    const n = vfs.readSync(fd, b, 0, len, pos);
    const exp = Math.max(0, Math.min(len, big.size - pos));
    if (n !== exp || sha(b.subarray(0, n)) !== sha(src.subarray(pos, pos + n))) rb++;
  }
  check(rb === 0, `VFS range reads ${rc.length - rb}/${rc.length} 一致 (${big.p}, ${big.size} B)`);
  vfs.close();
}

result.failures = failures;
result.totalMs = Math.round(performance.now() - T0);
console.log('RESULT ' + JSON.stringify(result));
if (A.out) fs.writeFileSync(A.out, JSON.stringify(result, null, 1));
await srv.close();
fs.rmSync(WORK, { recursive: true, force: true });
console.log(failures ? `FAILED: failures=${failures}` : 'ALL PASS failures=0');
process.exit(failures ? 1 : 0);
