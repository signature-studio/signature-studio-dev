// AudioWorklet 向け wasm ローダ (src/runtime/worklet_loader.ts + public/worklets/wasm-host-worklet.js) の e2e / 計測。
//   node tools/perf/loader/loader_e2e.mjs [--reps 5] [--quick] [--out <jsonl>]
// 1 条件 1 反復ごとに Chrome を新規起動 (NativeModule キャッシュを持ち越さない)。
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import module from 'node:module';
import { fileURLToPath } from 'node:url';
import { startServer } from '../harness/server.mjs';
import { launchChrome } from '../harness/cdp.mjs';
import { genWasm, makeRef } from './gen_wasm.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const a = process.argv.slice(2);
const opt = (k, d) => { const i = a.indexOf('--' + k); return i >= 0 ? a[i + 1] : d; };
const QUICK = a.includes('--quick');
const REPS = +opt('reps', QUICK ? 1 : 5);
const OUT = opt('out', path.join(here, 'work/loader_e2e.jsonl'));
const work = path.join(here, 'work');
fs.mkdirSync(path.join(work, 'src'), { recursive: true });
fs.mkdirSync(path.join(work, 'gen'), { recursive: true });
process.env.PERF_TMP ||= path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'perf');
fs.mkdirSync(process.env.PERF_TMP, { recursive: true });
fs.writeFileSync(OUT, '');

// TS → JS (型を消すだけ。ビルド成果物と同じソースを実行する)
const tsSrc = fs.readFileSync(path.join(root, 'src/runtime/worklet_loader.ts'), 'utf8');
fs.writeFileSync(path.join(work, 'src/worklet_loader.js'), module.stripTypeScriptTypes(tsSrc));

const SIZES = {
  small: { stages: 64 },
  big: { stages: 1000, nops: 200, filler: 90000, pad: 32 * 1024 * 1024 },
};
const refStages = {};
for (const [k, v] of Object.entries(SIZES)) {
  fs.writeFileSync(path.join(work, 'gen', `${k}.wasm`), genWasm(v));
  refStages[k] = v.stages;
}
fs.writeFileSync(path.join(work, 'gen', 'small_noreset.wasm'), genWasm({ ...SIZES.small, reset: false }));
fs.writeFileSync(path.join(work, 'gen', 'bad_abi.wasm'), Buffer.from([0, 0x61, 0x73, 0x6d, 1, 0, 0, 0]));

const srv = await startServer({
  '/h': here, '/s': path.join(work, 'src'), '/w': path.join(root, 'public/worklets'), '/g': path.join(work, 'gen'),
});

const results = [];
const fails = [];
const check = (name, ok, detail = '') => { (ok ? results : fails).push(name); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${detail}`); };
const med = (xs) => { const s = [...xs].sort((x, y) => x - y); return s[s.length >> 1]; };
const bitEq = (x, y) => x.length === y.length && x.every((v, i) => Math.fround(v) === Math.fround(y[i]));

// ブロック列検証: capture の in から参照モデルを回して out と bit 一致するか
function verify(res, stages, perturb = 0) {
  const ref = makeRef(stages);
  let mism = 0;
  for (const c of res.captures) {
    const inp = Float32Array.from(c.in);
    if (perturb) inp[0] = Math.fround(inp[0] + perturb);
    if (!bitEq(Array.from(ref(inp)), c.out)) mism++;
  }
  return { blocks: res.captures.length, mism, nonzero: res.captures[0].out.filter((v) => v !== 0).length };
}

async function once(cfg) {
  const b = await launchChrome({});
  const la = os.loadavg()[0];
  try {
    const p = await b.newPage(`${srv.url}/h/page.html`);
    const res = await p.eval(`run(${JSON.stringify({ ...cfg, wasm: `/g/${cfg.file}.wasm` })})`, { timeout: 120000 });
    res.loadavg = la; res.chrome = b.version.product;
    res.logs = p.logs.filter((l) => /EXC|error/i.test(l));
    return res;
  } finally { await b.close(); }
}

const t00 = Date.now();
const rows = [];
// 1) 機能検証 (small): Module 直 postMessage 不可 / bytes 経路 / detach / 出力の bit 一致
{
  const r = await once({ file: 'small', prewarmBlocks: 4, keepModule: true, probe: true });
  fs.appendFileSync(OUT, JSON.stringify({ kind: 'func', ...r }) + '\n');
  check('module-direct-postMessage-fails (messageerror)', r.moduleDirectPostFailed === true);
  check('bytes-transfer-detaches-main-buffer', r.detached === true);
  check('main-module-kept', r.mainModuleKept === true);
  check('ctx-running', r.ctxState === 'running' || r.ctxState === 'closed', r.ctxState);
  const v = verify(r, refStages.small);
  check('first-4-blocks-bitexact-vs-reference', v.blocks === 4 && v.mism === 0 && v.nonzero > 0, JSON.stringify(v));
  // ネガティブコントロール: 入力 1 サンプルを壊した参照では不一致になること
  const nv = verify(r, refStages.small, 0.001);
  check('negative-control: perturbed reference mismatches', nv.mism > 0, JSON.stringify(nv));
  console.log(`   small: compile ${r.load.compileMs} ms / instantiate ${r.load.instantiateMs} ms / prewarm [${r.load.prewarmMs}] / roundtrip ${r.load.roundtripMs.toFixed(1)} ms / load avg ${r.loadavg.toFixed(2)}`);
}
// ABI 違反は reject される (ネガティブ)
{
  let rejected = false, msg = '';
  try { const r = await once({ file: 'bad_abi', prewarmBlocks: 0 }); void r; } catch (e) { rejected = /ws_buffers|export missing/.test(e.message); msg = e.message.slice(0, 160); }
  check('abi-violation-rejects-with-message', rejected, msg);
}

// 2) 起動〜初回ブロック計測: size × {prewarm 0/8} × {keepModule off/on}
const conds = [];
for (const size of Object.keys(SIZES)) for (const prewarmBlocks of [0, 8]) for (const keepModule of [false, true]) {
  if (QUICK && size === 'big' && keepModule) continue;
  conds.push({ file: size, prewarmBlocks, keepModule });
}
const agg = {};
for (let rep = 0; rep < REPS; rep++) {
  for (const c of conds) {
    const r = await once(c);
    const key = `${c.file}/pw${c.prewarmBlocks}/keep${+c.keepModule}`;
    const v = verify(r, refStages[c.file]);
    if (v.mism) check(`bitexact ${key} rep${rep}`, false, JSON.stringify(v));
    fs.appendFileSync(OUT, JSON.stringify({ kind: 'timing', key, rep, ...r }) + '\n');
    (agg[key] ??= []).push(r);
  }
}
const f1 = (x) => (Number.isFinite(x) ? x.toFixed(1) : '-');
console.log(`\n| 条件 (size/prewarm/keepModule) | bytes | worklet compile ms | instantiate ms | prewarm 計 ms | roundtrip ms | main compile ms | load→first16 ms | block0 ms | max(16blk) ms |`);
console.log('|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|');
for (const [k, rs] of Object.entries(agg)) {
  const m = (f) => med(rs.map(f));
  console.log(`| ${k} | ${rs[0].bytes} | ${f1(m((r) => r.load.compileMs))} | ${f1(m((r) => r.load.instantiateMs))} | ${f1(m((r) => r.load.prewarmMs.reduce((s, x) => s + x, 0)))} | ${f1(m((r) => r.load.roundtripMs))} | ${f1(m((r) => r.load.mainCompileMs ?? NaN))} | ${f1(m((r) => r.loadToFirstBlocksMs))} | ${f1(m((r) => r.firstBlockMs))} | ${f1(m((r) => r.maxBlockMs))} |`);
}
console.log(`(各値 n=${REPS} の中央値; min–max は ${OUT} の jsonl から)`);
for (const [k, rs] of Object.entries(agg)) {
  const f = (g) => { const xs = rs.map(g); return `${f1(Math.min(...xs))}–${f1(Math.max(...xs))}`; };
  console.log(`  ${k}: block0 ${f((r) => r.firstBlockMs)} ms / max16 ${f((r) => r.maxBlockMs)} ms / worklet compile ${f((r) => r.load.compileMs)} ms / roundtrip ${f((r) => r.load.roundtripMs)} ms / startup→first16 ${f((r) => r.startupToFirstBlocksMs)} ms`);
}
console.log(`\nPASS ${results.length} / FAIL ${fails.length}  elapsed ${((Date.now() - t00) / 1000).toFixed(1)} s  loadavg-end ${os.loadavg()[0].toFixed(2)}`);
await srv.close();
process.exit(fails.length ? 1 : 0);
