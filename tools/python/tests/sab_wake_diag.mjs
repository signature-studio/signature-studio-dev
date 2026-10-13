// PY-8 (#80) 診断: SAB 同期 RPC 往復の「速い / 遅い」モードの切り分け。
//   node tests/sab_wake_diag.mjs [n=20000] [trials=5]
// host/rpc.mjs の RpcClient (worker, Atomics.wait) と RpcServer (main, Atomics.waitAsync) をそのまま使い、
// Python・flapi を抜いた素の往復だけを計る。往復ごとの時間を記録し、中央値・p90・遅い側 (中央値の 2 倍超) の比率を出す。
// 仮説: 遅いモードは server (waitAsync) が眠ってから起きるまでの wake 遅延で、Python/flapi の処理量とは無関係。
// 判定: Python 無しの素の往復が、flapi 込みの計測と同じ bimodal を示せば、遅さは RPC の wake 側にある。
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";
import { createRpcBuffer, RpcClient, RpcServer } from "../host/rpc.mjs";
import fs from "node:fs";

if (!isMainThread) {
  const { sab, n } = workerData;
  const c = new RpcClient(sab);
  const t = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const a = performance.now();
    c.call({ i });
    t[i] = (performance.now() - a) * 1000;
  }
  parentPort.postMessage(Array.from(t));
} else {
  const n = Number(process.argv[2] || 20000);
  const trials = Number(process.argv[3] || 5);
  const pct = (a, p) => a[Math.min(a.length - 1, Math.floor(a.length * p))];
  const runTrial = async () => {
    const sab = createRpcBuffer();
    const srv = new RpcServer(sab, async (m) => ({ i: m.i }));
    const w = new Worker(new URL(import.meta.url), { workerData: { sab, n } });
    const t = await new Promise((r, j) => { w.once("message", r); w.once("error", j); });
    srv.stop();
    await w.terminate();
    return t;
  };
  const report = [];
  for (let k = 0; k < trials; k++) {
    const t = (await runTrial()).sort((a, b) => a - b);
    const med = pct(t, 0.5);
    report.push({ median_us: +med.toFixed(2), p90_us: +pct(t, 0.9).toFixed(2), slow_ratio: +(t.filter((x) => x > 2 * med).length / t.length).toFixed(3) });
  }
  console.log(JSON.stringify({ n, trials, load: fs.readFileSync("/proc/loadavg", "utf8").trim(), report }));
}
