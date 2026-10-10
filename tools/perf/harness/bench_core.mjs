// node / Chrome 共用ベンチ中核 (ES module)。環境依存 (ファイル読込・createModule 取得) は呼出側。
export const BUDGET = { k44: 128 / 44100 * 1000, k48: 128 / 48000 * 1000 };   // ms / 128 frames

export const now = () => performance.now();

export function stats(arr) {
  const a = Float64Array.from(arr).sort();
  const n = a.length, q = (p) => a[Math.min(n - 1, Math.floor(p * n))];
  let s = 0; for (const v of a) s += v;
  return { n, min: a[0], p50: q(0.5), mean: s / n, p90: q(0.9), p99: q(0.99), p999: q(0.999), max: a[n - 1] };
}
export function rtf(ms) { return { k44: ms / BUDGET.k44, k48: ms / BUDGET.k48 }; }

const f32bits = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };

// ---- OTT (M10 lift) : processReplacing(128 frames) ----------------------
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;

export function ottInit(mod, { param = 0.5, N = 128 } = {}) {
  const t0 = now();
  if (mod._m6_data_install) mod._m6_data_install();
  const t1 = now();
  const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
  mod._function_18011d400(BigInt(OBJ), 0n);
  for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32bits(param));
  mod._function_180120800(BigInt(OBJ));
  U8[OBJ + 0x248] = 0;
  for (let i = 0; i < N; i++) {
    F32[(BUF >> 2) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
    F32[(BUF >> 2) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
  }
  U32[IN_A >> 2] = BUF; U32[(IN_A >> 2) + 2] = BUF + N * 4;
  U32[OU_A >> 2] = BUF + N * 8; U32[(OU_A >> 2) + 2] = BUF + N * 12;
  return { dataInstallMs: t1 - t0, initMs: now() - t1 };
}
export function ottBlock(mod, N = 128) {
  mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
}
export function ottChecksum(mod, N = 128) {
  const F32 = mod.HEAPF32; let nan = 0, big = 0, den = 0, zero = 0; let h = 0x811c9dc5;
  const U32 = mod.HEAPU32;
  for (let i = 0; i < 2 * N; i++) {
    const v = F32[(BUF >> 2) + 2 * N + i]; const b = U32[(BUF >> 2) + 2 * N + i];
    if (Number.isNaN(v)) nan++; else if (!Number.isFinite(v) || Math.abs(v) > 1e6) big++; else if (v === 0) zero++; else if (Math.abs(v) < 1.2e-38) den++;
    h = Math.imul(h ^ b, 16777619) >>> 0;
  }
  return { hash: h.toString(16), nan, big, denormal: den, zero };
}

// 時系列 (最初の `head` 呼出を個別に記録 → Liftoff→TurboFan 遷移を可視化) + 定常
export function runBlocks(call, { warmup = 200, iters = 5000, head = 0, batch = 1 } = {}) {
  const headT = [];
  for (let i = 0; i < head; i++) { const t = now(); call(); headT.push(now() - t); }
  for (let i = 0; i < warmup; i++) call();
  const per = new Float64Array(Math.ceil(iters / batch));
  for (let i = 0; i < per.length; i++) {
    const t = now(); for (let b = 0; b < batch; b++) call(); per[i] = (now() - t) / batch;
  }
  return { head: headT, steady: stats(per) };
}

// ---- M5 純計算カーネル (waveshaper a1 / distortion a2) ----------------
const SCR = 0x1000000, KADDR = 0x1000100;
export function m5Init(mod, which) {
  const F32 = mod.HEAPF32, U32 = mod.HEAPU32;
  const N = 128;
  for (let i = 0; i < N; i++) F32[(SCR >> 2) + i] = Math.fround(Math.sin(i * 0.07) * 1.3);
  if (which === 'a1') U32[KADDR >> 2] = Number(f32bits(0.5));
}
export function m5Block(mod, which, N = 128) {
  if (which === 'a1') mod._function_6a7540(BigInt(SCR), BigInt(N));
  else mod._function_6a2fb0(BigInt(SCR), BigInt(SCR + 0x20000), BigInt(N));
}

// 出力同値性署名: 先頭 8 ブロック + 1000 ブロック目の出力 bits を FNV で畳む。最適化水準が違っても
// (fast-math 無し / wasm に FMA 無し) bit 一致するはずなので、変種の健全性ガードに使う。
export function ottSignature(mod, N = 128) {
  const U32 = mod.HEAPU32; let h = 0x811c9dc5 >>> 0;
  const mix = () => { for (let i = 0; i < 2 * N; i++) h = Math.imul(h ^ U32[(BUF >> 2) + 2 * N + i], 16777619) >>> 0; };
  for (let b = 1; b <= 1000; b++) { ottBlock(mod, N); if (b <= 8 || b === 1000) mix(); }
  return h.toString(16);
}

export function m5Signature(mod, which, N = 128) {
  m5Init(mod, which); m5Block(mod, which, N);
  const U32 = mod.HEAPU32; const base = (which === 'a1' ? SCR : SCR + 0x20000) >> 2; let h = 0x811c9dc5 >>> 0;
  for (let i = 0; i < N; i++) h = Math.imul(h ^ U32[base + i], 16777619) >>> 0;
  m5Init(mod, which);
  return h.toString(16);
}
