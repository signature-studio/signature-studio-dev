// P8 実 OTT 版: bit-exact OTT (tools/ott x64c lift = ottl.cjs) を plugin 別 instance (各自の Memory) で N 個駆動する (node)。
//   node bench_real.mjs <ottl.cjs> <N> [BLK=1000] [REPS=7]
// 出力 1 行 JSON: 起動 (N 個の load+setup 時間, RSS 増分) / 定常 (instance 当たり µs/block の p50 = 1 block = 128f) / 署名。
// 署名は ott_x64c_bench.mjs と同一手順 (1000 block, 1..8 と 1000 番目を FNV) で、全 instance が一致し、既知値 6b1696f0 と一致すること。
import path from 'node:path';
import { load } from '../../../ott/diff/api.mjs';

const f = path.resolve(process.argv[2]); const n = Number(process.argv[3] || 1);
const BLK = Number(process.argv[4] || process.env.BLK || 1000), REPS = Number(process.argv[5] || process.env.REPS || 7);
const N = 128;
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const p50 = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };

const rss0 = process.memoryUsage().rss;
const t0 = performance.now();
const apis = [];
for (let i = 0; i < n; i++) apis.push(await load(f));
const tLoad = performance.now() - t0;
const rssLoad = process.memoryUsage().rss;

const t1 = performance.now();
for (const api of apis) {
  const mod = api.mod; const U32 = mod.HEAPU32, F32 = mod.HEAPF32;
  api.ctor(OBJ); for (let i = 0; i < 19; i++) api.setParam(OBJ, i, 0.5); api.resume(OBJ);
  for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
}
const tSetup = performance.now() - t1;

// 署名 (ott_x64c_bench.mjs と同一手順)
const sigs = [];
for (const api of apis) {
  const U32 = api.mod.HEAPU32; let h = 0x811c9dc5 >>> 0;
  for (let k = 1; k <= 1000; k++) { api.process(OBJ, IN_A, OU_A, N); if (k <= 8 || k === 1000) for (let i = 0; i < 2 * N; i++) h = Math.imul(h ^ U32[BUF / 4 + 2 * N + i], 16777619) >>> 0; }
  sigs.push(h.toString(16));
}

// 定常: rep ごとに全 instance を BLK block ずつ round-robin で処理し、instance 当たり µs/block を取る
for (const api of apis) for (let k = 0; k < 300; k++) api.process(OBJ, IN_A, OU_A, N);
const per = [];
for (let r = 0; r < REPS; r++) {
  const t = performance.now();
  for (let b = 0; b < BLK; b++) for (const api of apis) api.process(OBJ, IN_A, OU_A, N);
  per.push((performance.now() - t) * 1000 / (BLK * n));
}
const us = p50(per);

console.log(JSON.stringify({
  runtime: `node ${process.version}`, cfg: 'ott_plugin_instance', N: n, blk: BLK, reps: REPS,
  load_ms: +tLoad.toFixed(2), setup_ms: +tSetup.toFixed(2), rss_load_mib: +((rssLoad - rss0) / 2 ** 20).toFixed(1),
  rss_after_mib: +((process.memoryUsage().rss) / 2 ** 20).toFixed(1),
  us_per_block_p50: +us.toFixed(2), us_per_block_min: +Math.min(...per).toFixed(2), us_per_block_max: +Math.max(...per).toFixed(2),
  rtf44_per_instance: +(us / (N / 44.1 * 1000)).toFixed(5),
  sig: [...new Set(sigs)], sig_n: sigs.length,
}));
