// results/huge_*.jsonl → markdown
import { readJsonl, f, med } from './agg.mjs';
const MB = (b) => (b / 1048576).toFixed(1);
const say = (s = '') => console.log(s);
const rows = (n) => readJsonl(`huge_${n}.jsonl`);

function scale() {
  const r = rows('scale').filter((x) => !x.error); if (!r.length) return;
  say('\n#### H1. compile 時間スケーリング (M11 boot closure を K 倍複製; Chrome 154 headless=new, 16 コア)\n');
  say('| K | wasm MB | 関数数 | flags | 方式 | compile ms | instantiate ms | 初回 export 呼出 ms | wall ms | CPU 秒 | renderer RSS MB | HWM MB |');
  say('|--:|--:|--:|---|---|--:|--:|--:|--:|--:|--:|--:|');
  for (const x of r) say(`| ${x.k} | ${MB(x.fileBytes)} | ${8936 * x.k} | ${x.flags} | ${x.how} | ${f(x.compileMs, 0)} | ${f(x.instantiateMs, 0)} | ${f(x.firstCallMs, 1)} | ${f(x.wallMs, 0)} | ${f(x.cpuSec, 2)} | ${f(x.rendererRssMB, 0)} | ${f(x.rendererHwmMB, 0)} |`);
}
function cores() {
  const r = rows('cores').filter((x) => !x.error); if (!r.length) return;
  say('\n#### H2. コア数スケーリング (taskset)\n');
  say('| K | flags | CPUs | compile ms | instantiate ms | CPU 秒 | HWM MB |'); say('|--:|---|---|--:|--:|--:|--:|');
  for (const x of r) say(`| ${x.k} | ${x.flags} | ${x.cpus} | ${f(x.compileMs, 0)} | ${f(x.instantiateMs, 0)} | ${f(x.cpuSec, 2)} | ${f(x.rendererHwmMB, 0)} |`);
}
function hints() {
  const r = rows('hints').filter((x) => !x.error); if (!r.length) return;
  say('\n#### H3. compilationHints custom section\n');
  say('| hint | flags | compile ms | instantiate ms | 初回呼出 ms | CPU 秒 | HWM MB |'); say('|---|---|--:|--:|--:|--:|--:|');
  for (const x of r) say(`| ${x.hint} | ${x.flags} | ${f(x.compileMs, 0)} | ${f(x.instantiateMs, 0)} | ${f(x.firstCallMs, 1)} | ${f(x.cpuSec, 2)} | ${f(x.rendererHwmMB, 0)} |`);
}
function simple(name, title, cols) {
  const r = rows(name); if (!r.length) return;
  say(`\n#### ${title}\n`);
  say('| ' + cols.map((c) => c[0]).join(' | ') + ' |'); say('|' + cols.map(() => '---').join('|') + '|');
  for (const x of r) say('| ' + cols.map((c) => (typeof c[1] === 'function' ? c[1](x) : x[c[1]]) ?? '-').join(' | ') + ' |');
}
scale(); cores(); hints();
simple('limits', 'H4. モジュールサイズ上限 (compileStreaming)', [['cfg', 'cfg'], ['size B', 'size'], ['ok', (x) => x.error ? 'ERR' : x.ok], ['ms', (x) => f(x.ms, 0)], ['error', (x) => x.error || x.err || '']]);
simple('funcs', 'H5. 関数数上限', [['K', 'k'], ['funcs', 'funcs'], ['size MB', (x) => MB(x.size)], ['ok', (x) => x.error ? 'ERR' : x.ok], ['ms', (x) => f(x.ms, 0)], ['error', (x) => x.error || x.err || '']]);
simple('sync', 'H6. 同期 new WebAssembly.Module', [['cfg', 'cfg'], ['bytes', 'bytes'], ['ok', 'ok'], ['ms', (x) => f(x.ms, 1)], ['error', (x) => x.err || x.error || '']]);
simple('mem', 'H7. WebAssembly.Memory 確保', [['cfg', 'cfg'], ['ok', 'ok'], ['alloc ms', (x) => f(x.allocMs, 2)], ['touch ms', (x) => f(x.touchMs, 2)], ['bytes', 'bytes'], ['count', 'count'], ['err', (x) => x.err || x.error || ''], ['RSS MB', (x) => f(x.rendererRssMB, 0)], ['VmSize MB', (x) => f(x.rendererVmSizeMB, 0)]]);

function bw() {
  const r = rows('bw').filter((x) => !x.error); if (!r.length) return;
  say('\n#### H8. 帯域制限下の streaming vs bytes (K=10, 32.1MiB; 取得開始→compile 完了までの合計)\n');
  say('| 帯域 | flags | 方式 | fetch ms | compile ms | 合計 ms |'); say('|--:|---|---|--:|--:|--:|');
  for (const x of r) say(`| ${x.mbps} Mbps | ${x.flags} | ${x.how} | ${x.fetchMs ? f(x.fetchMs, 0) : '(overlap)'} | ${f(x.how === 'stream' ? null : x.compileMs, 0)} | ${f(x.totalMs, 0)} |`);
}
function ottscale() {
  const r = rows('ottscale').filter((x) => !x.error); if (!r.length) return;
  say('\n#### H9. 実行可能な K 倍 OTT (関数 144×K, Worker + emscripten glue instantiateStreaming; 起動→128f 処理)\n');
  say('| K | 関数数 | flags | create ms (fetch+compile+inst) | 初回 128f ms | 定常 p50 ms | p99 ms | CPU 秒 | HWM MB |'); say('|--:|--:|---|--:|--:|--:|--:|--:|--:|');
  for (const x of r) say(`| ${x.k} | ${144 * x.k} | ${x.flags} | ${f(x.createMs, 0)} | ${f(x.firstCallMs, 3)} | ${f(x.steady.p50, 4)} | ${f(x.steady.p99, 4)} | ${f(x.cpuSec, 2)} | ${f(x.rendererHwmMB, 0)} |`);
}
function worklet() {
  const r = rows('worklet').filter((x) => !x.error); if (!r.length) return;
  say('\n#### H10. AudioWorklet (実スレッド)\n');
  say('| wasm | flags | Module→worklet postMessage | main compile ms | worklet compile ms | worklet instantiate ms | 128f/call 平均 ms (1000 call 区間) | 2s 実時間 process() 回数 / 期待 |'); say('|---|---|---|--:|--:|--:|---|---|');
  for (const x of r) say(`| ${x.cfg.replace('worklet/', '')} | ${x.flags} | ${x.moduleToWorklet} | ${f(x.compileMsMainThread, 1)} | ${x.compileMsInWorklet} | ${x.instantiateMsInWorklet} | ${(x.workletChunkMeanMs || []).map((v) => v.toFixed(3)).slice(0, 4).join(', ')}… | ${x.rt?.calls} / ${x.rt?.expectedBlocks} |`);
}
function cache() {
  const r = rows('cache').filter((x) => !x.error); if (!r.length) return;
  say('\n#### H11. code cache / HTTP cache / Cache API (OTT K=400: 32.6MiB, 57,600 関数, 同一 profile で繰返し)\n');
  say('| 試行 | instantiateStreaming/create ms | 先頭 128f call ms | `Code Cache/wasm` エントリ数 | 備考 |'); say('|---|--:|---|--:|---|');
  for (const x of r) say(`| ${x.cfg} | ${f(x.instantiateStreamingMs ?? x.createMs, 1)} | ${(x.head || []).slice(0, 3).map((v) => v.toFixed(2)).join(', ')} | ${(x.wasmCacheFiles || []).filter((s) => !s.startsWith('index')).length} | ${x.cacheHit === undefined ? '' : 'Cache API hit=' + x.cacheHit} |`);
}
bw(); ottscale(); worklet(); cache();
simple('idb', 'H12. IndexedDB / structuredClone / postMessage', [['cfg', 'cfg'], ['IDB put Module', 'idbModule'], ['structuredClone', 'structuredClone'], ['postMessage→Worker', (x) => JSON.stringify(x.postMessageToWorker)], ['IDB bytes put ms', (x) => f(x.idbBytesPutMs, 0)], ['get ms', (x) => f(x.idbBytesGetMs, 0)], ['再 compile ms', (x) => f(x.recompileFromIdbMs, 0)]]);
