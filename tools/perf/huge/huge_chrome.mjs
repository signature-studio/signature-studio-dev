// Chrome 巨大 wasm / compile 実験オーケストレータ。
//   node huge_chrome.mjs <exp> [--k 1,4,10] [--mode stream,bytes] ...  → results/huge_<exp>.jsonl (追記)
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { startServer } from '../harness/server.mjs';
import { launchChrome } from '../harness/cdp.mjs';

const a = process.argv.slice(2);
const exp = a[0];
const opt = (k, d) => { const i = a.indexOf('--' + k); return i >= 0 ? a[i + 1] : d; };
const here = new URL('./', import.meta.url).pathname;
const WORK = path.resolve(here, '../work');
const RES = path.resolve(here, '../results');
fs.mkdirSync(RES, { recursive: true });
const jf = `${RES}/huge_${exp}.jsonl`;
const log = (o) => { fs.appendFileSync(jf, JSON.stringify(o) + '\n'); console.error(JSON.stringify(o).slice(0, 400)); };
const TICK = 100;
const cpuSec = (pid) => { try { const f = fs.readFileSync(`/proc/${pid}/stat`, 'utf8'); const p = f.slice(f.lastIndexOf(')') + 2).split(' '); return (+p[11] + +p[12]) / TICK; } catch { return null; } };
const rendererOf = (b) => b.procs().filter((x) => x.type === 'renderer').sort((x, y) => (cpuSec(y.pid) || 0) - (cpuSec(x.pid) || 0));

const FLAGS = {
  default: '', eager: '--no-wasm-lazy-compilation', lazy: '--wasm-lazy-compilation', liftoff: '--liftoff-only', tf: '--no-liftoff',
  notier: '--no-wasm-dynamic-tiering', lazyval: '--wasm-lazy-validation', hints: '--experimental-wasm-compilation-hints',
  eagerliftoff: '--no-wasm-lazy-compilation --liftoff-only',
  eagertf: '--no-wasm-lazy-compilation --no-liftoff',
  eagernotier: '--no-wasm-lazy-compilation --no-wasm-dynamic-tiering',
  eagerhints: '--no-wasm-lazy-compilation --experimental-wasm-compilation-hints',
};

const srv = await startServer({ '/w': WORK, '/h': path.resolve(here, '../harness'), '/hg': here, '/r': RES });

// 1 構成 = 新規 Chrome + 1 ページ。fn(page, browser) が結果オブジェクトを返す。
async function one(cfgName, fn, { flags = 'default', cpus = null, extraArgs = [], ud = null, page = '/hg/huge.html', keepUd = false } = {}) {
  const jsFlags = FLAGS[flags] ?? flags;
  const b = await launchChrome({ jsFlags, cpus, extraArgs, ud, keepUd });
  const la = os.loadavg()[0];
  try {
    const p = await b.newPage(`${srv.url}${page}`);
    const r0 = rendererOf(b)[0]; const c0 = r0 ? cpuSec(r0.pid) : null;
    const t0 = Date.now();
    const res = await fn(p, b);
    const wallMs = Date.now() - t0;
    const r1 = rendererOf(b)[0];
    const out = { exp, cfg: cfgName, flags, cpus, load: la, wallMs, ...res };
    if (r1) { out.rendererRssMB = r1.rssMB; out.rendererHwmMB = r1.hwmMB; out.rendererVmSizeMB = r1.vmsizeMB; out.cpuSec = c0 == null ? null : cpuSec(r1.pid) - c0; }
    out.chrome = b.version.product; out.v8 = b.version.jsVersion; out.ud = b.ud;
    log(out);
    return out;
  } catch (e) { log({ exp, cfg: cfgName, flags, cpus, error: String(e.message).slice(0, 400) }); }
  finally { await b.close(); }
}
const comp = (p, params) => p.eval(`exp.compile(${JSON.stringify(params)})`, { timeout: 900000 });
const bytesOf = (f) => fs.statSync(`${WORK}/huge/${f}`).size;
const url = (f, q = '') => `/w/huge/${f}${q}`;

const ks = opt('k', '1,4,10').split(',').map(Number);
const modes = opt('mode', 'stream').split(',');
const flagsList = opt('flags', 'default').split(',');
const reps = +opt('reps', 1);

function ensure(k, extra = []) {
  const name = `k${k}${extra.length ? '_' + extra.join('_').replace(/[^a-z0-9_]/gi, '') : ''}.wasm`;
  const f = `${WORK}/huge/${name}`;
  if (!fs.existsSync(f)) {
    const { execFileSync } = await_import_child();
    execFileSync('python3', [`${here}wasm_dup.py`, `${WORK}/inputs/m11/m11_boot.wasm`, f, '-k', String(k), ...extra], { stdio: 'inherit' });
  }
  return name;
}
import cp from 'node:child_process';
function await_import_child() { return cp; }

if (exp === 'scale') {
  for (const k of ks) { const f = ensure(k); for (const fl of flagsList) for (const m of modes) for (let r = 0; r < reps; r++) {
    await one(`k${k}/${m}`, (p) => comp(p, { url: url(f), how: m, callExport: 'm11_init_count' }).then((x) => ({ k, fileBytes: bytesOf(f), ...x })), { flags: fl });
  } }
} else if (exp === 'bw') {   // 帯域制限下の streaming vs bytes (compile が転送に隠れるか)
  const k = +opt('kk', 10); const f = ensure(k);
  for (const mbps of opt('mbps', '50,100,1000').split(',').map(Number)) for (const fl of flagsList) for (const m of modes) {
    const bps = Math.floor(mbps * 1e6 / 8);
    await one(`k${k}/${mbps}Mbps/${m}`, (p) => comp(p, { url: url(f, `?bps=${bps}`), how: m, instantiate: false }).then((x) => ({ k, mbps, ...x })), { flags: fl });
  }
} else if (exp === 'cores') {
  const k = +opt('kk', 10); const f = ensure(k);
  for (const cpus of opt('cpus', '0,0-1,0-3,0-7,0-15').split(',')) for (const fl of flagsList) for (let r = 0; r < reps; r++)
    await one(`k${k}/cpus${cpus}`, (p) => comp(p, { url: url(f), how: 'stream', callExport: 'm11_init_count' }).then((x) => ({ k, ...x })), { flags: fl, cpus });
} else if (exp === 'hints') {
  const k = +opt('kk', 10);
  for (const h of ['none', 'lazy', 'eager', 'bg', 'lazybase']) {
    const f = h === 'none' ? ensure(k) : ensure(k, ['--hint', h]);
    for (const fl of ['eager', 'eagerhints']) for (const m of ['stream'])
      await one(`k${k}/hint-${h}`, (p) => comp(p, { url: url(f), how: m, callExport: 'm11_init_count' }).then((x) => ({ k, hint: h, ...x })), { flags: fl });
  }
} else if (exp === 'limits') {
  const L = 1073741824;
  for (const [nm, pad] of [['Lm1', L - 1], ['L', L], ['Lp1', L + 1], ['L_plus1MB', L + 1048576], ['512MB', 536870912], ['768MB', 805306368]]) {
    const f = `pad_${nm}.wasm`;
    if (!fs.existsSync(`${WORK}/huge/${f}`)) cp.execFileSync('python3', [`${here}wasm_dup.py`, `${WORK}/inputs/m11/m11_boot.wasm`, `${WORK}/huge/${f}`, '-k', '1', '--pad-to', String(pad)], { stdio: 'inherit' });
    await one(`pad-${nm}`, async (p) => ({ size: bytesOf(f), ...(await p.eval(`exp.compileErr(${JSON.stringify({ url: url(f) })})`, { timeout: 600000 })) }));
    fs.rmSync(`${WORK}/huge/${f}`, { force: true });   // 1GB 級は使い捨て
  }
} else if (exp === 'sync') {
  const f = ensure(1); const g = ensure(4);
  for (const ff of [f, g]) {
    await one(`sync-main-${ff}`, (p) => p.eval(`exp.syncCompile(${JSON.stringify({ url: url(ff) })})`));
    await one(`sync-worker-${ff}`, (p) => p.eval(`exp.syncCompileWorker(${JSON.stringify({ url: url(ff) })})`));
  }
} else if (exp === 'funcs') {   // 関数数上限 (1,000,000)
  for (const k of (opt('k', '111,112').split(',').map(Number))) { const f = ensure(k);
    await one(`k${k}/funcs`, async (p) => ({ k, size: bytesOf(f), funcs: 8936 * k, ...(await p.eval(`exp.compileErr(${JSON.stringify({ url: url(f) })})`, { timeout: 900000 })) })); }
} else if (exp === 'idb') {
  for (const f of ['k1.wasm'].map((n) => (ensure(1), n))) await one('idb-module', (p) => p.eval(`exp.idbModule(${JSON.stringify({ url: url(f) })})`, { timeout: 300000 }));
  await one('idb-module-k10', (p) => p.eval(`exp.idbModule(${JSON.stringify({ url: url(ensure(10)) })})`, { timeout: 600000 }));
} else if (exp === 'mem') {
  for (const [nm, pages, max, sh] of [['16MB', 256, 0, false], ['256MB', 4096, 0, false], ['864MB(OTT現行)', 13824, 13824, false], ['2GB', 32768, 0, false], ['4GB', 65536, 0, false], ['864MB shared', 13824, 13824, true], ['4GB shared', 65536, 65536, true]]) {
    await one(`mem-${nm}`, async (p, b) => { const r = await p.eval(`exp.memoryAlloc(${JSON.stringify({ initialPages: pages, maximumPages: max, shared: sh })})`); return r; });
  }
  // 864MB メモリを何個作れるか
  await one('mem-count864', async (p) => {
    const r = await p.eval(`(() => { const o = []; let n = 0, err = ''; const t0 = performance.now(); try { for (; n < 200; n++) { const m = new WebAssembly.Memory({ initial: 13824, maximum: 13824 }); new Uint8Array(m.buffer)[4096] = 1; o.push(m); } } catch (e) { err = String(e).slice(0, 150); } window.__mm = o; return { count: n, err, ms: performance.now() - t0 }; })()`);
    return r;
  });
}

if (exp === 'worklet') {
  for (const v of opt('variants', 'o0,o2').split(',')) for (const fl of flagsList) for (let r = 0; r < reps; r++)
    await one(`worklet/${v}`, (p) => p.eval(`exp.worklet(${JSON.stringify({ wasmUrl: `/w/ott/${v}/ott.wasm`, sampleRate: +opt('sr', 48000), rtSeconds: 2 })})`, { timeout: 120000 }), { flags: fl, extraArgs: ['--autoplay-policy=no-user-gesture-required'] });
}
// 実行可能な K 倍 OTT (関数 144*K 個): 起動→最初の 128f→定常までの実時間, tier 挙動
function ottK(k) {
  const d = `${WORK}/ottk/o2_k${k}`;
  if (!fs.existsSync(`${d}/ott.wasm`)) {
    fs.mkdirSync(d, { recursive: true });
    fs.copyFileSync(`${WORK}/ott/o2/ott.mjs`, `${d}/ott.mjs`);
    cp.execFileSync('python3', [`${here}wasm_dup.py`, `${WORK}/ott/o2/ott.wasm`, `${d}/ott.wasm`, '-k', String(k)], { stdio: 'inherit' });
  }
  return `../ottk/o2_k${k}`;
}
if (exp === 'ottscale') {
  for (const k of ks) { const v = ottK(k); for (const fl of flagsList) for (let r = 0; r < reps; r++)
    await one(`ottk${k}`, (pg) => pg.eval(`runBench(${JSON.stringify({ kind: 'ott', variant: v, iters: 5000, head: 300 })})`, { timeout: 600000 }).then((x) => ({ k, ...x })), { flags: fl, page: '/h/bench.html' }); }
}
// code cache: HTTP キャッシュ可能 URL を 同一 profile で繰返しロード (Window/streaming 経路と Worker/glue 経路)
if (exp === 'cache') {
  const k = +opt('kk', 400); const v = ottK(k);
  srv.defaults.cc = 'public, max-age=3600';
  const fl = opt('flags', 'default');
  const ud1 = fs.mkdtempSync('/tmp/opencode/perf/udc-');
  const wasmUrl = `/w/ottk/o2_k${k}/ott.wasm`;
  const wcache = () => { try { return cp.execSync(`find "${ud1}/Default/Code Cache/wasm" -type f -printf '%P %s\\n' 2>/dev/null | sort`).toString().trim().split('\n').filter(Boolean); } catch { return []; } };
  const settle = async () => { let last = '', same = 0; const t0 = Date.now(); while (same < 4 && Date.now() - t0 < 25000) { const st = wcache().join(';'); if (st === last) same++; else { same = 0; last = st; } await new Promise((r) => setTimeout(r, 500)); } return Date.now() - t0; };
  const phases = +opt('phases', 4);
  for (let ph = 1; ph <= phases; ph++) {
    await one(`cache-window/${ph}`, async (pg) => {
      const r = await pg.eval(`exp.rawRun(${JSON.stringify({ url: wasmUrl, iters: 30000 })})`, { timeout: 600000 });
      const w = await settle(); return { ...r, settleMs: w, wasmCacheFiles: wcache() };
    }, { flags: fl, ud: ud1, keepUd: true });
  }
  // Cache Storage (Cache API) 経由
  const ccache = () => { try { return cp.execSync(`find "${ud1}/Default/Service Worker/CacheStorage" -type f -printf '%P %s\\n' 2>/dev/null | sort | tail -12`).toString().trim().split('\n').filter(Boolean); } catch { return []; } };
  for (let ph = 1; ph <= 3; ph++) {
    await one(`cacheapi-window/${ph}`, async (pg) => {
      const r = await pg.eval(`exp.rawRun(${JSON.stringify({ url: wasmUrl, iters: 30000, cacheApi: true })})`, { timeout: 600000 });
      await settle(); await new Promise((r2) => setTimeout(r2, 2500)); return { ...r, cacheStorageFiles: ccache() };
    }, { flags: fl, ud: ud1, keepUd: true });
  }
  srv.defaults.cc = 'no-store';
  for (let ph = 1; ph <= 2; ph++) {
    srv.defaults.cc = 'public, max-age=3600';
    await one(`cache-worker/${ph}`, (pg) => pg.eval(`runBench(${JSON.stringify({ kind: 'ott', variant: v, iters: 30000, head: 300 })})`, { timeout: 600000 }).then(async (x) => ({ ...x, settleMs: await settle(), wasmCacheFiles: wcache() })), { flags: fl, page: '/h/bench.html', ud: ud1, keepUd: true });
  }
  fs.rmSync(ud1, { recursive: true, force: true });
}
await srv.close();
process.exit(0);
