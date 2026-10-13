// fle_lto_bench.mjs — PERF-P9 (#168) ④: flelift closure の最適化 variant 別 実行時間と出力一致。
//   node tools/flelift/fle_lto_bench.mjs <variant.cjs> [reps]
// 入力: _UStrAsg (0x4133f0) と Move (0x409c80) を固定入力で繰返し呼び、出力メモリの FNV-1a ハッシュを取る。
// 同じ入力・同じ hash なら variant 間で結果が一致する (署名)。時間は呼出の中央値 (µs)。
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const cjs = process.argv[2];
const reps = Number(process.argv[3] ?? 2000);
const m = await (await import(pathToFileURL(cjs).href)).default();
m._fle_data_install(); m._fle_init();
const U8 = m.HEAPU8, dv = new DataView(U8.buffer);
const slot = 0x20000000, str = 0x20001000 + 12, src = 0x20002000, dst = 0x20003000;
const N = [0x188, 0x40, 0x24, 0x18, 3, 1, 0];

const times = [];
const hasher = createHash('sha256');
function once(i) {
  const n = N[i % N.length];
  for (let k = 0; k < n; k++) U8[src + k] = (k * 7 + 3 + i) & 0xff;
  U8.fill(0xcc, dst, dst + n + 64);
  dv.setInt32(str - 8, 1, true); dv.setBigUint64(slot, 0n, true);
  const t0 = performance.now();
  m._fle_run(0x4133f0, BigInt(slot), BigInt(str), 0n, 0n, 0n, 0n, 0n, 0n);
  m._fle_run(0x409c80, BigInt(src), BigInt(dst), BigInt(n), 0n, 0n, 0n, 0n, 0n);
  times.push((performance.now() - t0) * 1000);
  return n;
}
for (let i = 0; i < 200; i++) once(i); // warm-up
times.length = 0;
for (let i = 0; i < reps; i++) {
  once(i);
  const n = N[i % N.length];
  hasher.update(U8.subarray(dst, dst + n));
  hasher.update(U8.subarray(slot, slot + 8));
}
times.sort((a, b) => a - b);
const med = times[times.length >> 1];
console.log(JSON.stringify({ variant: cjs, reps, p50_us: +med.toFixed(3), p90_us: +times[Math.floor(times.length * 0.9)].toFixed(3), sig: hasher.digest('hex').slice(0, 16) }));
