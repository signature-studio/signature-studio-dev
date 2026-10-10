import { runBench } from "./ott_bench.mjs";
import { runMemBench } from "./membench_run.mjs";
const get = async (u) => new Uint8Array(await (await fetch(u)).arrayBuffer());
self.onmessage = async () => {
  try {
    const r = { chrome: navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] };
    r.mem = await runMemBench(await get("/work/bench/mem32.wasm"), await get("/work/bench/mem64.wasm"), { reps: 9 });
    r.ott = await runBench(await get("/work/bench/ott32.wasm"), await get("/work/bench/ott64.wasm"), { iters: 500, reps: 15 });
    postMessage({ ok: true, r });
  } catch (e) { postMessage({ ok: false, err: String(e && e.stack || e) }); }
};
