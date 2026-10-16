// P23 (#3680): 1 Memory に畳んだ fold.wasm (Fresh Air + OTT) を 1 instance で駆動し、両 plugin の署名を取る (node)。
//   node tools/perf/p20/fold_sig.mjs [fold.cjs] [SCEN=400] [SEED=64030]   (NEG=1 で Fresh Air の入力を変える。OTT 側は変えない)
// 基準 (単独 instance): Fresh Air 5e5287b5 (fa_gain_sig.mjs 400・seed 64030) / OTT 6b1696f0 (ott_x64c_bench.mjs)。
// FA の入力生成は fa_gain_sig.mjs と同じ。OTT は ott_x64c_bench.mjs と同じ手順 (ctor・setParam 19 個・resume・process 1000 回)。
// 共有 static データの汚染は、畳み込み後の署名が単独基準と一致することで見る。
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const CJS = path.resolve(process.argv[2] || path.join(HERE, 'work/fold/fold.cjs'));
const SCEN = Number(process.argv[3] || 400);
let seed = Number(process.argv[4] || 64030) >>> 0;
const NEG = process.env.NEG === '1';
const NEG_OTT = process.env.NEG_OTT === '1';

const FA_SHIFT = 0x17e000000;
const FA_ENTRY = 0x180afe090 - FA_SHIFT;
const OTT_BASE = 0x30000000;
const OTT_RUN = (va) => OTT_BASE + (va - 0x180000000);

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
m._ott_data_install();

const U8 = () => new Uint8Array(m.HEAPU8.buffer);
const DV = () => new DataView(m.HEAPU8.buffer);
const zalloc = (n) => {
  const p = m._malloc(n);
  U8().fill(0, p, p + n);
  return p;
};

// FA: fa_gain_sig.mjs と同じ手順
function faSig() {
  const sigs = [];
  let changed = 0;
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
    m._fle_run(FA_ENTRY, BigInt(T), BigInt(CX), 0n, 0n, 0n, 0n, 0n, 0n);
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
  let sig = 0x811c9dc5;
  for (const h of sigs) sig = fnv(sig, [h & 255, (h >>> 8) & 255, (h >>> 16) & 255, h >>> 24]);
  return { sig: sig.toString(16).padStart(8, '0'), uniq: new Set(sigs).size, changed };
}

// OTT: ott_x64c_bench.mjs と同じ手順。バッファは malloc (fold 内で FA の領域と重ならないように)。
const big = (x) => BigInt.asUintN(64, BigInt(x));
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const ottRun = (va, a, x = []) => BigInt.asUintN(64, BigInt(m._ott_run(OTT_RUN(va), big(a[0] ?? 0), big(a[1] ?? 0), big(a[2] ?? 0), big(a[3] ?? 0), big(x[0] ?? 0), big(x[1] ?? 0), big(x[2] ?? 0), big(x[3] ?? 0))));
function ottSig() {
  const N = 128;
  const OBJ = zalloc(0x40000), IN_A = zalloc(32), OU_A = zalloc(32), BUF = zalloc(4 * N * 4);
  const U32 = () => new Uint32Array(m.HEAPU8.buffer), F32 = () => new Float32Array(m.HEAPU8.buffer);
  ottRun(0x18011d400, [OBJ, 0]);
  for (let i = 0; i < 19; i++) ottRun(0x180120af0, [OBJ, i], [0, 0, f32b(NEG_OTT ? 0.6 : 0.5)]);
  ottRun(0x180120800, [OBJ]);
  for (let i = 0; i < N * 2; i++) F32()[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
  U32()[IN_A / 4] = BUF; U32()[IN_A / 4 + 2] = BUF + N * 4; U32()[OU_A / 4] = BUF + N * 8; U32()[OU_A / 4 + 2] = BUF + N * 12;
  let h = 0x811c9dc5 >>> 0;
  for (let k = 1; k <= 1000; k++) {
    ottRun(0x18011ec20, [OBJ, IN_A, OU_A, N]);
    if (k <= 8 || k === 1000) for (let i = 0; i < 2 * N; i++) h = Math.imul(h ^ U32()[BUF / 4 + 2 * N + i], 16777619) >>> 0;
  }
  let nz = 0;
  for (let i = 0; i < 2 * N; i++) if (F32()[BUF / 4 + 2 * N + i] !== 0) nz++;
  return { sig: h.toString(16), nonzeroOut: nz };
}

const fa = faSig();
const ott = ottSig();
console.log(JSON.stringify({
  mode: 'fold_single_memory', neg: NEG, neg_ott: NEG_OTT, scen: SCEN, seed: Number(process.argv[4] || 64030),
  fa_sig: fa.sig, fa_sig_unique_per_scen: fa.uniq, fa_out_changed: fa.changed,
  ott_sig: ott.sig, ott_nonzeroOut: ott.nonzeroOut,
  fa_match: fa.sig === '5e5287b5', ott_match: ott.sig === '6b1696f0',
}));
