// 実 Emscripten ランタイム (stdio/FS) 上で createEmscriptenFs が動くことの検証 (node, fetcher=worker_threads)。
//   node test/emscripten-test.ts --pkg work/pkg-t1
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { Worker } from 'node:worker_threads';
import { spawnServer } from './spawn-server.ts';
import { fetchManifest, openVfs, loadNodeDecoders } from '../vfs/index.ts';
import type { WorkerLike } from '../vfs/index.ts';
import { openNodeSyncFile } from '../vfs/node-file.ts';
import { createEmscriptenFs } from '../vfs/emscripten.ts';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..');
const PKG = path.resolve(root, A.pkg ?? 'work/pkg-t1');
const W = path.join(root, 'work', 'emprobe');
fs.mkdirSync(W, { recursive: true });
execFileSync('bash', ['-lc', `source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; emcc test/emscripten/probe.c -O1 -o work/emprobe/probe.mjs -sMODULARIZE=1 -sEXPORT_ES6=1 -sENVIRONMENT=node -sFORCE_FILESYSTEM=1 -sEXPORTED_RUNTIME_METHODS=FS,callMain -sINVOKE_RUN=0 -sEXIT_RUNTIME=0`], { cwd: root, stdio: 'inherit' });

await loadNodeDecoders();
const srv = await spawnServer(PKG);
const manifest = await fetchManifest(srv.url);
const spawn = (): WorkerLike => {
  const w = new Worker(new URL('../vfs/fetch-worker.ts', import.meta.url));
  w.unref();
  return { postMessage: (m) => w.postMessage(m), terminate: () => void w.terminate(), onMessage: (cb) => void w.on('message', cb) };
};
const cacheFile = path.join(W, 'cache.bin');
fs.rmSync(cacheFile, { force: true });
const { vfs, ready } = openVfs({ baseUrl: srv.url + '/', manifest, cacheFile: openNodeSyncFile(cacheFile), loader: 'sab', spawn, nodeDecoders: true, verify: true });
await ready;

// 対象: 大きめの既存ファイル
const inv = fs.readFileSync(path.join(root, 'work/inv_win.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
const target = inv.filter((e: any) => e.cat !== 'exec' && vfs.statSync(e.p)?.size === e.size && e.size > 5e6).sort((a: any, b: any) => b.size - a.size)[0];
const dir = path.posix.dirname(target.p);
const want = fs.readFileSync(target.disk);
let h = 2166136261 >>> 0;
for (const b of want) h = Math.imul(h ^ b, 16777619) >>> 0;
const wantFnv = h.toString(16).padStart(8, '0');

const { default: createProbe } = await import(path.join(W, 'probe.mjs'));
const lines: string[] = [];
const mod = await createProbe({ noInitialRun: true, print: (s: string) => lines.push(s), printErr: (s: string) => lines.push('ERR ' + s) });
mod.FS.mkdir('/fl');
mod.FS.mount(createEmscriptenFs(mod.FS, vfs), {}, '/fl');
const rc = mod.callMain(['/fl/' + target.p, '/fl/' + dir]);
console.log(lines.join('\n'));
let failed = 0;
const ok = (c: boolean, m: string) => {
  console.log(c ? '  ok  ' : '  FAIL', m);
  if (!c) failed++;
};
ok(rc === 0, 'main rc=0');
ok(lines.some((l) => l.includes(`size=${want.length}`) && l.includes(`ftell=${want.length}`) && l.includes(`fnv=${wantFnv}`)), `fread/fseek/ftell via Emscripten FS match (${target.p}, ${(want.length / 1e6).toFixed(1)} MB, fnv=${wantFnv})`);
ok(lines.some((l) => l.includes('b5=' + [...want.subarray(5, 9)].map((x) => x.toString(16).padStart(2, '0')).join(''))), 'fseek+fread random position');
ok(lines.some((l) => /^DIR entries=\d+/.test(l) && Number(/entries=(\d+)/.exec(l)![1]) >= 3), 'opendir/readdir');
ok(lines.some((l) => l.includes(`STAT rc=0 size=${want.length} isreg=1`)), 'stat');
ok(lines.includes('MISSING ENOENT'), 'ENOENT');
ok(lines.includes('WRITE denied'), 'write denied (read-only)');
vfs.close();
await srv.close();
fs.rmSync(cacheFile, { force: true });
console.log(failed ? `FAILED: ${failed}` : 'ALL PASS');
process.exit(failed ? 1 : 0);
