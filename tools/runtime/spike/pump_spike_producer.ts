// producer worker: ring (atomics/native) か MessagePort (asyncify/jspi) へ送り、ack を Atomics.wait で待って RTT を測る。
import { PumpRing } from "../../../src/runtime/worker_pump";
type Cfg = { variant: string; depth: number; ackSab: SharedArrayBuffer; ackIndex: number; ring?: { sab: SharedArrayBuffer; byteOffset: number }; port?: MessagePort; n: number; burst: number; phases: string[] };
let ack!: Int32Array, ackIdx = 0, ring: PumpRing | null = null, port: MessagePort | null = null;
const send = (msg: number, seq: number) => {
  const tPost = performance.timeOrigin + performance.now();
  if (ring) { while (!ring.push({ message: msg, ptx: seq, tPost })) { /* full: consumer が掃けるまで spin */ } } else port!.postMessage({ msg, seq, tPost });
};
const waitAck = (seq: number) => {
  for (;;) { const v = Atomics.load(ack, ackIdx); if (v === seq) return; Atomics.wait(ack, ackIdx, v, 5000); }
};
const q = (a: number[], p: number) => a[Math.min(a.length - 1, Math.floor(a.length * p))];
self.onmessage = (ev: MessageEvent<Cfg>) => {
  const c = ev.data;
  ack = new Int32Array(c.ackSab); ackIdx = c.ackIndex;
  ring = c.ring ? new PumpRing(c.ring.sab, c.ring.byteOffset) : null; port = c.port ?? null;
  const out: Record<string, unknown> = { variant: c.variant, depth: c.depth };
  let seq = 0;
  if (c.phases.includes("pingpong")) {
    for (let i = 0; i < 200; i++) { seq++; send(1, seq); waitAck(seq); } // warmup
    const rtt: number[] = [];
    for (let i = 0; i < c.n; i++) { seq++; const t0 = performance.now(); send(1, seq); waitAck(seq); rtt.push((performance.now() - t0) * 1000); }
    rtt.sort((a, b) => a - b);
    out.rttUs = { n: rtt.length, p50: +q(rtt, 0.5).toFixed(1), p90: +q(rtt, 0.9).toFixed(1), p99: +q(rtt, 0.99).toFixed(1), max: +rtt[rtt.length - 1].toFixed(1), mean: +(rtt.reduce((a, b) => a + b, 0) / rtt.length).toFixed(1) };
  }
  if (c.phases.includes("nested")) {
    // [2: ネスト開始, 1, 1, 4: ネスト終了, 1] 各々 ack を待つ。2 は内側ポンプに入る前に ack されないので、最初の 1 の ack から数える
    seq++; send(2, seq); waitAck(seq); // 外側 dispatch が ack してからネスト ポンプへ入る
    for (let i = 0; i < 2; i++) { seq++; send(1, seq); waitAck(seq); } // 内側ポンプで処理
    seq++; send(4, seq); waitAck(seq); // 内側ポンプ終了
    seq++; send(1, seq); waitAck(seq); // 外側ポンプに復帰して処理
    out.nestedOk = true;
  }
  if (c.phases.includes("burst")) {
    const t0 = performance.now();
    for (let i = 0; i < c.burst; i++) { seq++; send(1, seq); }
    waitAck(seq);
    const ms = performance.now() - t0;
    out.burst = { events: c.burst, ms: +ms.toFixed(1), eventsPerSec: Math.round(c.burst / (ms / 1000)) };
  }
  if (c.phases.includes("quit")) send(0xffff, ++seq);
  (self as unknown as Worker).postMessage({ t: "result", out });
};
