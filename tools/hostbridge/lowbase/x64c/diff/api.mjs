// api.mjs: 2 種の wasm build (旧 RetDec chain: _function_<va> export / 新 lifter: _ott_run) を同一 API で駆動する。
// lowbase 版: V-shift 先 LB_BASE を env (LB_BASE) で受ける。ott_run の VA は LB_BASE + RVA。
export const LB_BASE = Number(process.env.LB_BASE ?? 0x10000);
export async function load(path) {
  const m2 = await import(path);
  const mod = await (m2.default ? m2.default() : m2());
  if (mod._m6_data_install) mod._m6_data_install();
  if (mod._ott_data_install) mod._ott_data_install();
  const lifted = !!mod._ott_run;
  const big = (x) => BigInt(x);
  const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
  const api = { mod, lifted, f32b };
  if (lifted) {
    const run = (va, a, x = []) => BigInt.asUintN(64, mod._ott_run(LB_BASE + (va - 0x180000000), big(a[0] ?? 0), big(a[1] ?? 0), big(a[2] ?? 0), big(a[3] ?? 0), big(x[0] ?? 0), big(x[1] ?? 0), big(x[2] ?? 0), big(x[3] ?? 0)));
    api.ctor = (obj) => run(0x18011d400, [obj, 0]);
    api.setParam = (obj, i, v) => run(0x180120af0, [obj, i], [0, 0, f32b(v)]);
    api.resume = (obj) => run(0x180120800, [obj]);
    api.process = (obj, inA, ouA, n) => run(0x18011ec20, [obj, inA, ouA, n]);
    api.run = run;
  } else {
    api.ctor = (obj) => mod._function_18011d400(big(obj), 0n);
    api.setParam = (obj, i, v) => mod._function_180120af0(big(obj), big(i), f32b(v));
    api.resume = (obj) => mod._function_180120800(big(obj));
    api.process = (obj, inA, ouA, n) => mod._function_18011ec20(big(obj), big(inA), big(ouA), big(n));
  }
  return api;
}
