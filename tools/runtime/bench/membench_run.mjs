// node / browser 共通: wasm32 vs wasm64 マイクロベンチ
export async function runMemBench(b32, b64, { reps = 7 } = {}) {
  const mk = async (bytes) => { const { instance } = await WebAssembly.instantiate(bytes, {}); instance.exports._initialize?.(); instance.exports.init(); return instance.exports; };
  const E = { wasm32: await mk(b32), wasm64: await mk(b64) };
  const cases = { seq_sum: 8, rand_rmw: 20_000_000, chase: 10_000_000, hot_loop: 200_000, call_mix: 50_000_000 };
  const out = {};
  for (const [fn, n] of Object.entries(cases)) {
    const t = { wasm32: [], wasm64: [] }; const chk = {};
    for (let rep = 0; rep < reps + 1; rep++) for (const k of (rep % 2 ? ["wasm32", "wasm64"] : ["wasm64", "wasm32"])) {
      const t0 = performance.now(); chk[k] = E[k][fn](n); const ms = performance.now() - t0;
      if (rep > 0) t[k].push(ms);
    }
    const med = (a) => a.slice().sort((x, y) => x - y)[a.length >> 1];
    out[fn] = { n, ms32: +med(t.wasm32).toFixed(1), ms64: +med(t.wasm64).toFixed(1), min32: +Math.min(...t.wasm32).toFixed(1), min64: +Math.min(...t.wasm64).toFixed(1) };
    out[fn].ratio_med = +(out[fn].ms64 / out[fn].ms32).toFixed(3); out[fn].ratio_min = +(out[fn].min64 / out[fn].min32).toFixed(3);
  }
  return out;
}
