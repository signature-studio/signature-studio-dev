// PY-8 (#80) 診断: SAB 同期 RPC の往復時間と、呼出しの間隔 (gap) の関係。
//   node tests/rpc_gap_diag.mjs [n=2000] [trials=3] [gapsMs=0,0.02,0.1,0.5,2] [mode=sleep|spin]
// host/rpc.mjs の RpcClient (worker) と RpcServer (main, waitAsync) を使い、Python・flapi を抜いた素の往復を計る。
// gap > 0 のときは、呼出しの間を待つ。mode=sleep は worker が Atomics.wait で眠る (worker も server も idle)、
// mode=spin は worker が回し続ける (worker は起きたまま、server だけが要求待ちで idle)。
// 仮説: 実運用の MIDI は間隔をあけて届くため、idle 後に起きる wake が遅い (100µs 台の遅い峰の正体)。
// 判定: gap が長いほど中央値・p90・60µs 超の比率が上がれば、遅さは idle 後の wake にある。
//       spin でも遅れが残れば server 側の wake、消えれば worker 側の wake。gap=0 は連続呼出しの対照。
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";
import { createRpcBuffer, RpcClient, RpcServer } from "../host/rpc.mjs";
import fs from "node:fs";

if (!isMainThread) {
  const { sab, n, gapMs, mode } = workerData;
  const c = new RpcClient(sab);
  const sleepCell = new Int32Array(new SharedArrayBuffer(4));
  const t = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    if (gapMs > 0 && mode === "spin") {
      const end = performance.now() + gapMs;
      while (performance.now() < end);
    } else if (gapMs > 0) Atomics.wait(sleepCell, 0, 0, gapMs);
    const a = performance.now();
    c.call({ i });
    t[i] = (performance.now() - a) * 1000;
  }
  parentPort.postMessage(Array.from(t));
} else {
  const n = Number(process.argv[2] || 2000);
  const trials = Number(process.argv[3] || 3);
  const gaps = (process.argv[4] || "0,0.02,0.1,0.5,2").split(",").map(Number);
  const mode = process.argv[5] || "sleep";
  const pct = (a, p) => a[Math.min(a.length - 1, Math.floor(a.length * p))];
  const runTrial = async (gapMs) => {
    const sab = createRpcBuffer();
    const srv = new RpcServer(sab, async (m) => ({ i: m.i }));
    const w = new Worker(new URL(import.meta.url), { workerData: { sab, n, gapMs, mode } });
    const t = await new Promise((r, j) => { w.once("message", r); w.once("error", j); });
    srv.stop();
    await w.terminate();
    return t;
  };
  const report = [];
  for (const gapMs of gaps) {
    const trialsOut = [];
    for (let k = 0; k < trials; k++) {
      const t = (await runTrial(gapMs)).sort((a, b) => a - b);
      trialsOut.push({
        median_us: +pct(t, 0.5).toFixed(2),
        p90_us: +pct(t, 0.9).toFixed(2),
        over60_ratio: +(t.filter((x) => x > 60).length / t.length).toFixed(3),
      });
    }
    report.push({ gap_ms: gapMs, trials: trialsOut });
  }
  console.log(JSON.stringify({ n, trials, mode, load: fs.readFileSync("/proc/loadavg", "utf8").trim(), report }));
}
