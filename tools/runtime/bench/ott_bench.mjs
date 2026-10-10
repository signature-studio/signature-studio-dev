// wasm32 vs wasm64 の OTT DSP (lifted) 実負荷比較。node / browser 共通 (export runBench)。
import { loadOtt, makeRunner } from "./ott_driver.mjs";
export async function runBench(b32, b64, { iters = 500, reps = 21 } = {}) {
  const out = {};
  const rs = {};
  for (const [name, bytes] of [["wasm32", b32], ["wasm64", b64]]) {
    const o = await loadOtt(bytes); rs[name] = makeRunner(o); rs[name].setup(0.5);
    out[name] = { times: [] };
  }
  // 順序バイアスを避けて交互実行
  for (let rep = 0; rep < reps + 1; rep++) {
    for (const name of (rep % 2 ? ["wasm32", "wasm64"] : ["wasm64", "wasm32"])) {
      const r = rs[name]; r.setup(0.5);
      const t0 = performance.now();
      for (let i = 0; i < iters; i++) r.process();
      const ms = performance.now() - t0;
      if (rep > 0) out[name].times.push(ms); // rep0 = warmup
      out[name].hash = r.hash();
    }
  }
  for (const k of Object.keys(out)) {
    const t = out[k].times.sort((a, b) => a - b);
    out[k].medianMs = t[t.length >> 1]; out[k].minMs = t[0];
    out[k].usPerBlock = +(out[k].medianMs * 1000 / iters).toFixed(3);
  }
  out.ratio64over32_median = +(out.wasm64.medianMs / out.wasm32.medianMs).toFixed(3);
  out.hashEqual = out.wasm32.hash === out.wasm64.hash;
  return out;
}
