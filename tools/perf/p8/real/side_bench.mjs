// P8 実 OTT 版 (PIC 税・#1201): 相対化 lift を SIDE_MODULE にして dlopen で 1 instance 駆動する node 計測。
//   node side_bench.mjs <side dir (host.cjs と side.wasm)> [BLK=1000] [REPS=7]
//   SIDE_NEG=skip_data_install で ott_data_install を省く (署名が 6b1696f0 から外れることの確認用)
// 出力 1 行 JSON。bench_real.mjs と同じ手順 (署名 = 1000 block の FNV、既知値 6b1696f0 と一致すること、定常 = 1 block = 128f の p50)。
// 同じ相対化 lift の静的 (非 PIC) 版 (bench_real.mjs) との比が PIC 税。N は 1 のみ (1 つの side module を 1 回 dlopen するため)。
import fs from 'node:fs';
import path from 'node:path';

const dir = path.resolve(process.argv[2]);
const BLK = Number(process.argv[3] || process.env.BLK || 1000), REPS = Number(process.argv[4] || process.env.REPS || 7);
const N = 128;
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const p50 = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };
const big = (x) => BigInt(x);
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };

const m2 = await import(path.join(dir, 'host.cjs'));
const createHost = m2.default || m2;
const rss0 = process.memoryUsage().rss;
const t0 = performance.now();
const mod = await createHost();
mod.FS.writeFile('/side.wasm', fs.readFileSync(path.join(dir, 'side.wasm')));
if (!mod._host_load()) throw new Error('host_load: ' + mod.UTF8ToString(mod._host_error()));
mod._host_set_gbase(big(0x30000000));
if (process.env.SIDE_NEG !== 'skip_data_install') mod._host_data_install(); // ネガティブコントロール: 省くと署名が変わることを確かめる
const tLoad = performance.now() - t0;
const rssLoad = process.memoryUsage().rss;

const run = (va, a, x = []) => BigInt.asUintN(64, mod._host_run(0x30000000 + (va - 0x180000000), big(a[0] ?? 0), big(a[1] ?? 0), big(a[2] ?? 0), big(a[3] ?? 0), big(x[0] ?? 0), big(x[1] ?? 0), big(x[2] ?? 0), big(x[3] ?? 0)));
const api = {
  ctor: (obj) => run(0x18011d400, [obj, 0]),
  setParam: (obj, i, v) => run(0x180120af0, [obj, i], [0, 0, f32b(v)]),
  resume: (obj) => run(0x180120800, [obj]),
  process: (obj, inA, ouA, n) => run(0x18011ec20, [obj, inA, ouA, n]),
};

const t1 = performance.now();
const U32 = mod.HEAPU32, F32 = mod.HEAPF32;
api.ctor(OBJ); for (let i = 0; i < 19; i++) api.setParam(OBJ, i, 0.5); api.resume(OBJ);
for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
const tSetup = performance.now() - t1;

let h = 0x811c9dc5 >>> 0;
for (let k = 1; k <= 1000; k++) { api.process(OBJ, IN_A, OU_A, N); if (k <= 8 || k === 1000) for (let i = 0; i < 2 * N; i++) h = Math.imul(h ^ U32[BUF / 4 + 2 * N + i], 16777619) >>> 0; }
const sig = h.toString(16);

for (let k = 0; k < 300; k++) api.process(OBJ, IN_A, OU_A, N);
const per = [];
for (let r = 0; r < REPS; r++) {
  const t = performance.now();
  for (let b = 0; b < BLK; b++) api.process(OBJ, IN_A, OU_A, N);
  per.push((performance.now() - t) * 1000 / BLK);
}
const us = p50(per);

console.log(JSON.stringify({
  runtime: `node ${process.version}`, cfg: 'ott_side_module_hidden', N: 1, blk: BLK, reps: REPS,
  load_ms: +tLoad.toFixed(2), setup_ms: +tSetup.toFixed(2), rss_load_mib: +((rssLoad - rss0) / 2 ** 20).toFixed(1),
  us_per_block_p50: +us.toFixed(2), us_per_block_min: +Math.min(...per).toFixed(2), us_per_block_max: +Math.max(...per).toFixed(2),
  rtf44_per_instance: +(us / (N / 44.1 * 1000)).toFixed(5),
  sig: [sig], sig_n: 1,
}));
