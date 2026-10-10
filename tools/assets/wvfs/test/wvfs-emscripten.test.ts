// Emscripten FS アダプタ (createWvfsFs) の node 実機検証。
//   node wvfs/test/wvfs-emscripten.test.ts
// 実 Emscripten ランタイム (emcc 6.0.12) に /c/home・/c/tmp (Wvfs) と /fl (MEMFS = 読取系 mount との共存)
// を mount し、C stdio の読み書き + FS.syncfs(false) の物理 flush を検証する。
//   前提: emsdk (/opt/emsdk)。出力は wvfs/work/emprobe/ (gitignore)。
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { Wvfs, NodeBackend, createWvfsFs } from '../index.ts';

const root = path.join(path.dirname(new URL(import.meta.url).pathname), '..', '..'); // tools/assets
const W = path.join(root, 'wvfs', 'work', 'emprobe');
const STORE = path.join(W, 'store');
fs.rmSync(W, { recursive: true, force: true });
fs.mkdirSync(STORE, { recursive: true });

try {
  execFileSync('bash', ['-lc', `source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; emcc wvfs/test/probe-wvfs.c -O1 -sASSERTIONS=2 -o wvfs/work/emprobe/probe.mjs -sMODULARIZE=1 -sEXPORT_ES6=1 -sENVIRONMENT=node -sFORCE_FILESYSTEM=1 -sEXPORTED_RUNTIME_METHODS=FS,callMain -sINVOKE_RUN=0 -sEXIT_RUNTIME=0`], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
} catch (e: any) {
  console.error(String(e.stderr ?? e));
  throw e;
}

let failed = 0;
const ok = (c: boolean, m: string) => {
  console.log(c ? '  ok  ' : '  FAIL', m);
  if (!c) failed++;
};

// store#1: C から見える初期 state (JS 書込 → mount → C 読み)
const home1 = await Wvfs.open(new NodeBackend(path.join(STORE, 'home')));
const tmp1 = await Wvfs.open(new NodeBackend(path.join(STORE, 'tmp')));
home1.mkdirpSync('/probe/dir');
home1.writeFileSync('/fromjs.bin', new TextEncoder().encode('FROM-JS'));
tmp1.mkdirpSync('/');
void tmp1;

const { default: createProbe } = await import(path.join(W, 'probe.mjs'));
const lines: string[] = [];
const mod = await createProbe({ noInitialRun: true, print: (s: string) => lines.push(s), printErr: (s: string) => lines.push('ERR ' + s) });
const FS = mod.FS;
FS.mkdir('/fl');
FS.mount(FS.filesystems.MEMFS, {}, '/fl'); // 読取系 mount との共存 (実運面では /fl = LazyVfs)
FS.writeFile('/fl/seed.txt', new TextEncoder().encode('SEED-FL'));
FS.mkdir('/c');
FS.mkdir('/c/home');
FS.mkdir('/c/tmp');
FS.mount(createWvfsFs(FS, home1, { stores: [home1, tmp1] }), {}, '/c/home');
FS.mount(createWvfsFs(FS, tmp1, { stores: [home1, tmp1] }), {}, '/c/tmp');

const rc = mod.callMain([]);
console.log(lines.join('\n'));
ok(rc === 0, 'main rc=0');
ok(lines.some((l) => l === 'FL=SEED-FL'), 'C stdio reads /fl (MEMFS coexistence)');
ok(lines.some((l) => l === 'RT=HELLO-WVFS match=1'), 'C stdio write→read via /c/home (Wvfs)');
ok(lines.some((l) => l === 'JS=FROM-JS'), 'C reads a file written by JS (Wvfs index → journal read)');

// FS.syncfs(false) = flush 契約の FS.syncfs 相当口。open ままの fddirty をジャーナルへ
const syncfs = () => new Promise<number | null>((res) => FS.syncfs(false, (e: number | null) => res(e)));
const syncErr = await syncfs();
ok(syncErr === null, `FS.syncfs(false) → ${syncErr === null ? 'null' : syncErr}`);
// 既存 mount を開いたままページが死ぬ想定: store を閉じて再オープン (reload)
await home1.close();
await tmp1.close();

const home2 = await Wvfs.open(new NodeBackend(path.join(STORE, 'home')));
const tmp2 = await Wvfs.open(new NodeBackend(path.join(STORE, 'tmp')));
ok(new TextDecoder().decode(home2.readFileSync('/probe/dir/hello.bin')) === 'HELLO-WVFS', 'C-written file persisted across reload (Wvfs journal)');
ok(tmp2.readFileSync('/t.bin').length === 4, 'C-written /c/tmp file persisted');
ok(new TextDecoder().decode(home2.readFileSync('/fromjs.bin')) === 'FROM-JS', 'JS-written file persisted');
ok(home2.readdirSync('/probe/dir').length === 1, 'tree after reload');
await home2.close();
await tmp2.close();

console.log(failed ? `FAILED: ${failed}` : 'ALL PASS');
process.exit(failed ? 1 : 0);
