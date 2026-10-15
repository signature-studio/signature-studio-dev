// P20 (#2963): Fresh Air GainDsp::process の x64c wasm を単独 instance で駆動し、出力の署名を取る (node)。
//   node tools/perf/p20/fa_gain_sig.mjs [fa.cjs] [SCEN=400] [SEED=64030]   (NEG=1 で 1 パラメタを変えるネガティブコントロール)
// 入力の分布は tools/liftlib/specs/fa_gain.json の vars・buffers に従う。L/R の sample 生成器は仕様に定義が無いため
// 一様 [-1, 1] の f32 を使う (本 harness の選択)。署名は L/R・this の状態スカラ (0xa0..0xd8)・buf の内容の FNV-1a。
// 構造体のポインタ値は署名に入れない (メモリ配置に依存するため。畳み込み後の比較でも同じ値になる)。
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const CJS = path.resolve(process.argv[2] || path.join(HERE, 'work/fa/fa.cjs'));
const SCEN = Number(process.argv[3] || 400);
let seed = Number(process.argv[4] || 64030) >>> 0;
const NEG = process.env.NEG === '1';

const SHIFT = 0x17e000000;
const ENTRY = 0x180afe090 - SHIFT;

function rnd() {
  seed = (seed + 0x6d2b79f5) >>> 0;
  let t = seed;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
const unif = (a, b) => a + (b - a) * rnd();
const int = (a, b) => a + Math.floor(rnd() * (b - a + 1));
const choice = (xs) => xs[Math.floor(rnd() * xs.length)];

function gen() {
  const v = {};
  v.mode = choice([0, 1]);
  v.ga = unif(0, 4);
  v.gb = unif(0, 4);
  v.n = rnd() < 0.5 ? choice([0, 1, 2, 3, 7, 16, 31, 64]) : int(1, 128);
  v.first = choice([1, 0, 0, 0]);
  const tgt = v.mode === 1 ? v.gb * 2 : v.ga;
  const kind = unif(0, 1);
  v.prev = kind < 0.2 ? tgt : kind < 0.3 ? tgt + 1e-40 : unif(0, 4);
  v.cur = unif(0, 4);
  v.g0 = unif(0, 4);
  v.c1 = unif(0, 1);
  v.c2 = unif(0, 1);
  v.mL = unif(0, 2);
  v.mR = unif(0, 2);
  v.f93 = choice([1, 1, 0, 0, 0]);
  v.fdb = choice([1, 1, 0, 0, 0]);
  v.v50 = unif(-2, 2);
  v.v98 = unif(-2, 2);
  if (NEG) v.ga += 0.5;
  return v;
}

const fnv = (h, bytes) => {
  for (const b of bytes) h = Math.imul(h ^ b, 16777619) >>> 0;
  return h;
};

const createModule = require(CJS);
const m = await createModule();
m._fle_init();
m._fle_data_install();

const U8 = () => new Uint8Array(m.HEAPU8.buffer);
const DV = () => new DataView(m.HEAPU8.buffer);
const zalloc = (n) => {
  const p = m._malloc(n);
  U8().fill(0, p, p + n);
  return p;
};

const sigs = [];
let changed = 0;
const t0 = performance.now();
for (let s = 0; s < SCEN; s++) {
  const v = gen();
  const n = v.n;
  const T = zalloc(256), PP = zalloc(40960), QQ = zalloc(128), BB = zalloc(32), CX = zalloc(48);
  const LA = zalloc(4 * n + 4), RA = zalloc(4 * n + 4);
  const dv = DV();
  for (let i = 0; i < n + 1; i++) {
    dv.setFloat32(LA + 4 * i, unif(-1, 1), true);
    dv.setFloat32(RA + 4 * i, unif(-1, 1), true);
  }
  const L0 = U8().slice(LA, LA + 4 * n + 4);
  dv.setBigUint64(T + 0x90, BigInt(PP), true);
  dv.setUint8(T + 0xb0, v.first);
  dv.setFloat32(T + 0xa8, v.prev, true);
  dv.setFloat32(T + 0xac, v.cur, true);
  dv.setFloat32(T + 0xa4, v.g0, true);
  dv.setFloat32(T + 0xbc, v.c1, true);
  dv.setFloat32(T + 0xc0, v.mL, true);
  dv.setFloat32(T + 0xcc, v.c2, true);
  dv.setFloat32(T + 0xd0, v.mR, true);
  dv.setUint32(PP + 0x9dc4, v.mode, true);
  dv.setFloat32(PP + 0x9e0c, v.ga, true);
  dv.setFloat32(PP + 0x9e18, v.gb, true);
  dv.setUint8(PP + 0x9e93, v.f93);
  dv.setUint8(PP + 0x9edb, v.fdb);
  dv.setFloat32(PP + 0x9e50, v.v50, true);
  dv.setFloat32(PP + 0x9e98, v.v98, true);
  dv.setBigUint64(PP + 0x9f30, BigInt(QQ), true);
  dv.setBigUint64(QQ + 0x28, BigInt(BB), true);
  dv.setBigUint64(QQ + 0x30, BigInt(BB), true);
  dv.setBigUint64(QQ + 0x38, BigInt(BB + 8), true);
  dv.setBigUint64(CX, BigInt(LA), true);
  dv.setBigUint64(CX + 8, BigInt(RA), true);
  dv.setUint32(CX + 0x28, n, true);

  m._fle_run(ENTRY, BigInt(T), BigInt(CX), 0n, 0n, 0n, 0n, 0n, 0n);

  const LN = U8().slice(LA, LA + 4 * n + 4);
  if (LN.some((b, i) => b !== L0[i])) changed++;
  const u8 = U8();
  let h = 0x811c9dc5;
  h = fnv(h, u8.subarray(LA, LA + 4 * n + 4));
  h = fnv(h, u8.subarray(RA, RA + 4 * n + 4));
  h = fnv(h, u8.subarray(T + 0xa0, T + 0xd8));
  h = fnv(h, u8.subarray(BB, BB + 32));
  sigs.push(h);
}
const ms = performance.now() - t0;
let sig = 0x811c9dc5;
for (const h of sigs) sig = fnv(sig, [h & 255, (h >>> 8) & 255, (h >>> 16) & 255, h >>> 24]);
console.log(JSON.stringify({
  runtime: `node ${process.version}`, mode: 'fa_gain_single_instance', neg: NEG, scen: SCEN, seed: Number(process.argv[4] || 64030),
  sig: sig.toString(16).padStart(8, '0'), sig_unique_per_scen: new Set(sigs).size, out_changed: changed, run_ms: +ms.toFixed(1),
}));
