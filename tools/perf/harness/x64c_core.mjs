// bit-exact OTT (tools/ott x64c lift の wasm) を emscripten glue 無しで駆動する共通中核。
// node / Chrome Dedicated Worker / AudioWorklet で同一コードを使う (環境依存は bytes の取得と now() のみ呼出側)。
// wasm は tools/perf/build/ott_x64c_build.sh の出力 (work/ott_x64c/<v>.wasm; import は env/wasi の 5 本のみ → stub)。
export const N = 128;
export const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const va = (rva) => 0x30000000 + (rva - 0x180000000);
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };

export function stubImports(mod) {
  const imp = {};
  for (const i of WebAssembly.Module.imports(mod)) { imp[i.module] ??= {}; imp[i.module][i.name] = i.kind === 'function' ? () => 0 : undefined; }
  return imp;
}

// -O3 系の emcc は export 名を minify する (例: ott_run → "l")。 glue (.cjs) から名前対応を引いた <v>.names.json を渡す
// (x64c_names.mjs が生成)。 minify されない変種 (o0〜o2lto) は恒等。
export const IDENT_NAMES = { memory: 'memory', ctors: '__wasm_call_ctors', ott_data_install: 'ott_data_install', ott_run: 'ott_run' };

export async function setupOtt(mod, names = IDENT_NAMES) {
  const inst = await WebAssembly.instantiate(mod, stubImports(mod));
  const e = inst.exports;
  const x = { memory: e[names.memory], ott_run: e[names.ott_run] };
  e[names.ctors](); e[names.ott_data_install]();
  const U32 = new Uint32Array(x.memory.buffer), F32 = new Float32Array(x.memory.buffer);
  const run = (rva, a = [], xs = []) => BigInt.asUintN(64, x.ott_run(va(rva), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), BigInt(a[2] ?? 0), BigInt(a[3] ?? 0), BigInt(xs[0] ?? 0), BigInt(xs[1] ?? 0), BigInt(xs[2] ?? 0), BigInt(xs[3] ?? 0)));
  run(0x18011d400, [OBJ, 0]);
  for (let i = 0; i < 19; i++) run(0x180120af0, [OBJ, i], [0, 0, f32b(0.5)]);
  run(0x180120800, [OBJ]);
  for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
  const PV = va(0x18011ec20), A0 = BigInt(OBJ), A1 = BigInt(IN_A), A2 = BigInt(OU_A), A3 = BigInt(N), Z = 0n;
  const call = () => x.ott_run(PV, A0, A1, A2, A3, Z, Z, Z, Z);
  // ott_x64c_bench.mjs と同じ署名: 1000 ブロック処理し先頭 8 + 1000 ブロック目の出力 FNV (gate の期待値 6b1696f0)
  const signature = () => {
    let h = 0x811c9dc5 >>> 0;
    for (let k = 1; k <= 1000; k++) { call(); if (k <= 8 || k === 1000) for (let i = 0; i < 2 * N; i++) h = Math.imul(h ^ U32[BUF / 4 + 2 * N + i], 16777619) >>> 0; }
    return h.toString(16);
  };
  const nonzero = () => { let nz = 0; for (let i = 0; i < 2 * N; i++) if (F32[BUF / 4 + 2 * N + i] !== 0) nz++; return nz; };
  return { x, call, signature, nonzero, memBytes: x.memory.buffer.byteLength };
}

export function stats(arr) {
  const a = Float64Array.from(arr).sort();
  const n = a.length, q = (p) => a[Math.min(n - 1, Math.floor(p * n))];
  let s = 0; for (const v of a) s += v;
  return { n, min: a[0], p50: q(0.5), mean: s / n, p90: q(0.9), p99: q(0.99), p999: q(0.999), max: a[n - 1] };
}

// now() は ms を返す関数。head = 最初の呼出を個別計時 (tier-up 遷移の可視化), steady = warmup 後の個別計時 B 回,
// batch64 = 64 call 平均を 100 回 (timer 分解能が粗い環境 (cross-origin isolated でも 5 µs) 向け)。
export function measure(call, now, { warmup = 300, iters = 20000, head = 300 } = {}) {
  const headT = [];
  for (let i = 0; i < head; i++) { const t = now(); call(); headT.push(now() - t); }
  for (let i = 0; i < warmup; i++) call();
  const per = new Float64Array(iters);
  for (let i = 0; i < iters; i++) { const t = now(); call(); per[i] = now() - t; }
  const b = new Float64Array(100);
  for (let i = 0; i < 100; i++) { const t = now(); for (let k = 0; k < 64; k++) call(); b[i] = (now() - t) / 64; }
  return { head: headT, steady: stats(per), batch64: stats(b) };
}
